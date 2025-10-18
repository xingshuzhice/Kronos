# Model 模块代码逻辑详解

## 概述

此目录包含 Kronos 金融预测模型的核心实现，分为三个主要部分：
1. **`__init__.py`** - 模型注册与工厂模式
2. **`kronos.py`** - 核心模型类、分词器、预测器和推理逻辑
3. **`module.py`** - 底层 Transformer 组件和量化模块

---

## 文件结构与职责

### 1. `__init__.py` - 模型工厂

**职责**：提供模型类的统一入口和动态加载机制。

```python
model_dict = {
    'kronos_tokenizer': KronosTokenizer,
    'kronos': Kronos,
    'kronos_predictor': KronosPredictor
}
```

**核心函数**：
- `get_model_class(model_name)` - 根据名称获取模型类

**用法示例**：
```python
from model import get_model_class
TokenizerClass = get_model_class('kronos_tokenizer')
```

---

### 2. `kronos.py` - 主模型实现

#### 2.1 KronosTokenizer 类

**目的**：使用二进制球形量化（BSQ）将连续 OHLCV 数据分词为离散标记。

**架构**：
- **编码器**（Encoder）：多层 Transformer 块，将输入嵌入到高维空间
- **量化层**（Quantization）：通过 BSQuantizer 将嵌入量化为 (s1, s2) 标记对
- **解码器**（Decoder）：多层 Transformer 块，从量化表示重建数据

**关键方法**：

| 方法 | 功能 |
|------|------|
| `forward(x)` | 完整编码-量化-解码流程，返回重建、损失和量化索引 |
| `encode(x, half=False)` | 仅编码，返回量化索引 |
| `decode(x, half=False)` | 仅解码，从索引恢复数据 |
| `indices_to_bits(x, half=False)` | 将整数索引转换为双极位表示 (-1, 1) |

**工作流程**：

```
Input (B, T, d_in)
    ↓
Linear Embedding (d_in → d_model)
    ↓
Encoder Blocks × (n_enc_layers - 1)
    ↓
Quantization Projection (d_model → codebook_dim = s1 + s2)
    ↓
BSQuantizer → [s1_bits | s2_bits] quantized codes
    ↓
Post-Quantization Processing
    ├─ Pre-part: s1_bits → Linear → Decoder → Output
    └─ Full: codebook_dim → Linear → Decoder → Output
    ↓
Output (B, T, d_in)
```

**重要属性**：
- `s1_bits`, `s2_bits`：分别控制预量化和后量化维度
- `codebook_dim = s1_bits + s2_bits`：量化空间总维度
- 编码器和解码器都有 `n_enc_layers - 1` 个块（去掉初始嵌入层）

---

#### 2.2 Kronos 类（主模型）

**目的**：自回归 Transformer，预测未来的 (s1, s2) 标记对。

**架构**：
- **分层嵌入**（HierarchicalEmbedding）：独立的 s1 和 s2 嵌入，通过融合投影合并
- **时间嵌入**（TemporalEmbedding）：编码时间特征（分钟、小时、星期几、日期、月份）
- **Transformer 块**：n_layers 个自注意力块处理序列
- **依赖感知层**（DependencyAwareLayer）：交叉注意力，条件化 s2 预测
- **双头输出**（DualHead）：分别输出 s1 和 s2 logits

**关键方法**：

| 方法 | 功能 | 返回值 |
|------|------|--------|
| `forward(s1_ids, s2_ids, stamp, padding_mask, use_teacher_forcing, s1_targets)` | 完整前向传播，同时预测 s1 和 s2 | (s1_logits, s2_logits) |
| `decode_s1(s1_ids, s2_ids, stamp, padding_mask)` | 仅预测 s1，返回上下文 | (s1_logits, context) |
| `decode_s2(context, s1_ids, padding_mask)` | 条件化预测 s2（需要 s1 上下文） | s2_logits |

**前向流程**：

```
[s1_ids, s2_ids] → HierarchicalEmbedding
    ↓
+ TemporalEmbedding(stamp)
    ↓
Token Dropout
    ↓
Transformer Blocks × n_layers (self-attention)
    ↓
RMSNorm
    ↓
DualHead.forward(x) → s1_logits
    ↓
[采样 s1 或使用 teacher forcing]
    ↓
DependencyAwareLayer(context, sampled_s1_embed)
    ↓
DualHead.cond_forward(x2) → s2_logits
```

**重要特性**：
- **Teacher Forcing**：训练时可用真实 s1 标记条件化 s2 预测
- **采样策略**：推理时从 s1 logits 中采样，再条件化 s2
- **权重初始化**：Xavier 正态初始化用于线性层，正态初始化用于嵌入

---

#### 2.3 辅助函数

| 函数 | 功能 |
|------|------|
| `top_k_top_p_filtering(logits, top_k, top_p)` | 实现 top-k 和核采样过滤 |
| `sample_from_logits(logits, temperature, top_k, top_p)` | 从 logits 中按规则采样 |
| `auto_regressive_inference(...)` | 自回归生成：逐步生成 pred_len 个标记对 |
| `calc_time_stamps(x_timestamp)` | 从时间戳提取 5 个时间特征 |

**auto_regressive_inference 核心逻辑**：

```python
# 准备
x_token = tokenizer.encode(x, half=True)  # 编码历史 → [s1_token, s2_token]

for i in range(pred_len):
    # 获取动态时间戳（滑动窗口）
    stamp = get_dynamic_stamp(x_stamp, y_stamp, current_seq_len, i)

    # 限制序列长度到 max_context
    if current_seq_len > max_context:
        input_tokens = [t[:, -max_context:] for t in x_token]

    # 预测 s1
    s1_logits, context = model.decode_s1(input_tokens[0], input_tokens[1], stamp)
    s1_sample = sample_from_logits(s1_logits[:, -1, :], T, top_k, top_p)

    # 预测 s2
    s2_logits = model.decode_s2(context, s1_sample)
    s2_sample = sample_from_logits(s2_logits[:, -1, :], T, top_k, top_p)

    # 追加到序列
    x_token[0] = cat([x_token[0], s1_sample], dim=1)
    x_token[1] = cat([x_token[1], s2_sample], dim=1)

# 解码并平均采样
z = tokenizer.decode(input_tokens, half=True)  # → (batch, sample_count, pred_len, feat)
preds = mean(z, axis=1)  # 跨采样平均
```

**关键点**：
- **采样计数**：同一序列生成 `sample_count` 个独立样本，然后平均以提高鲁棒性
- **动态上下文**：利用 max_context 限制 GPU 内存，同时维持足够历史
- **滑动窗口**：新预测标记逐步添加，旧标记可能被丢弃

---

#### 2.4 KronosPredictor 类

**目的**：高级推理 API，处理数据预处理、规范化、批量预测。

**初始化参数**：
```python
KronosPredictor(model, tokenizer, device="cuda:0", max_context=512, clip=5)
```

**关键方法**：

| 方法 | 功能 |
|------|------|
| `predict(df, x_timestamp, y_timestamp, pred_len, ...)` | 单序列预测 |
| `predict_batch(df_list, x_timestamp_list, y_timestamp_list, ...)` | 批量并行预测 |
| `generate(...)` | 内部：张量化推理主干 |

**predict() 工作流**：

```
Input DataFrame (价格列必需)
    ↓
补充缺失的 volume/amount 列
    ↓
提取时间戳特征 (minute, hour, weekday, day, month)
    ↓
合并 OHLCV 列 → 数组 (seq_len, 6)
    ↓
Z-score 归一化：x = (x - mean) / (std + 1e-5)
    ↓
裁剪到 [-clip, clip]（默认 ±5σ）
    ↓
batch 维度 (1, seq_len, 6) 和时间戳 (1, seq_len/pred_len, 5)
    ↓
generate() → 推理
    ↓
反归一化：preds * (std + 1e-5) + mean
    ↓
Output DataFrame (列: open, high, low, close, volume, amount)
```

**predict_batch() 特点**：
- 要求所有输入序列长度一致
- 堆叠为 (B, seq_len, 6) 批次进行并行处理
- 每个序列单独维持 mean/std 用于反归一化
- 返回列表，顺序与输入一致

**数据验证**：
- 必需列：`['open', 'high', 'low', 'close']`
- 可选列：`volume`, `amount`（缺失时填 0）
- 禁止 NaN 值

---

### 3. `module.py` - 底层组件

#### 3.1 量化模块

**BinarySphericalQuantizer (BSQ)**：
- 基于论文：https://arxiv.org/pdf/2406.07548.pdf
- 将向量量化为双极值 {-1, 1}

**BSQuantizer 包装**：
```python
class BSQuantizer(nn.Module):
    def forward(self, z, half=False):
        # 如果 half=True：分离 s1 和 s2 索引
        # 返回: (bsq_loss, quantized, z_indices)
```

**工作流程**：
```
Input z (B, T, codebook_dim)
    ↓
L2 归一化
    ↓
BinarySphericalQuantizer.quantize()
    ├─ zhat = sign(z) 即 {-1, 1}
    └─ 使用 STE（直通估计）以支持梯度
    ↓
计算损失：commit_loss + entropy_loss
    ↓
返回量化、损失、索引
```

**熵损失**（soft_entropy）：
- 按样本熵（per-sample）：衡量单个样本内各维度的分布
- 码簿熵（codebook）：衡量整体码簿的使用均匀性
- 总损失 = gamma0 * per_sample_H - gamma * codebook_H

---

#### 3.2 Transformer 组件

**RMSNorm**：
- 根均方正态化，比 LayerNorm 更高效
- `output = (x / RMS(x)) * weight`

**FeedForward**：
- SwiGLU 激活：`output = w2(SiLU(w1(x)) * w3(x))`
- 无偏差线性层

**RotaryPositionalEmbedding (RoPE)**：
- 旋转位置嵌入
- 独立缓存 cos/sin 矩阵用于高效计算

**MultiHeadAttentionWithRoPE**：
```
输入 x (B, T, d_model)
    ↓
Q, K, V 投影 + 多头分割
    ↓
RoPE 旋转编码位置信息
    ↓
缩放点积注意力（带因果掩码）
    ↓
多头合并 + 输出投影 + 残差
```

**MultiHeadCrossAttentionWithRoPE**：
- 查询、键、值来自不同源（用于依赖感知层）
- 同样支持 RoPE

---

#### 3.3 嵌入模块

**HierarchicalEmbedding**：
```python
def forward(self, [s1_ids, s2_ids]):
    s1_emb = emb_s1(s1_ids) * √d_model
    s2_emb = emb_s2(s2_ids) * √d_model
    return fusion_proj(concat([s1_emb, s2_emb], dim=-1))
```
- 融合投影：(d_model * 2) → d_model

**TemporalEmbedding**：
- 5 个时间维度：minute (60), hour (24), weekday (7), day (32), month (13)
- 可选可学习或固定（FixedEmbedding 用正弦编码）
- 最后相加：`output = minute + hour + weekday + day + month`

**FixedEmbedding**：
- 基于正弦/余弦位置编码
- `w[n, 2d] = sin(n / 10000^(2d/d_model))`
- `w[n, 2d+1] = cos(n / 10000^(2d/d_model))`

---

#### 3.4 专门层

**DependencyAwareLayer**：
```python
def forward(self, hidden_states, sibling_embed, key_padding_mask=None):
    # query = sibling_embed (来自另一子标记，如 s1)
    # key, value = hidden_states (来自 Transformer 上下文)
    attn_out = cross_attn(query=sibling_embed, key=hidden_states, value=hidden_states)
    return norm(hidden_states + attn_out)  # 残差连接
```
- 用途：s2 标记学习依赖 s1 标记的表示

**TransformerBlock**：
```
x → Norm → Self-Attention → + x
  → Norm → FeedForward → + x
```
- 前置正态化（Pre-LN）架构

**DualHead**：
```python
def forward(x):
    return proj_s1(x)  # s1 logits

def cond_forward(x2):
    return proj_s2(x2)  # s2 logits

def compute_loss(s1_logits, s2_logits, s1_targets, s2_targets):
    ce_s1 = cross_entropy(s1_logits, s1_targets)
    ce_s2 = cross_entropy(s2_logits, s2_targets)
    return (ce_s1 + ce_s2) / 2
```
- 支持可选 padding_mask 来忽略填充标记

---

## 数据流完整示例

### 推理流程

```python
# 1. 加载
tokenizer = KronosTokenizer.from_pretrained("...")
model = Kronos.from_pretrained("...")
predictor = KronosPredictor(model, tokenizer, device="cuda:0")

# 2. 预测（单序列）
pred_df = predictor.predict(
    df=historical_ohlcv,          # (seq_len, 6)
    x_timestamp=hist_timestamps,  # (seq_len,)
    y_timestamp=future_timestamps, # (pred_len,)
    pred_len=pred_len,
    T=1.0,                        # 温度
    top_p=0.9                     # 核采样
)
# 输出：pred_df (pred_len, 6)
```

**内部过程**：

```
Input: historical_ohlcv (400, 6), future_len = 120

↓ [KronosPredictor.predict]
  - 验证列
  - 补充 volume/amount
  - 提取时间特征

↓ [Normalize]
  x_norm = (x - mean) / (std + 1e-5)
  x_norm = clip(x_norm, -5, 5)

↓ [KronosPredictor.generate]
  - 转为张量
  - 复制 sample_count 次（默认 1）

↓ [auto_regressive_inference]
  - tokenizer.encode(x_norm) → [s1_token, s2_token]
  - 循环 120 次：
    ├─ model.decode_s1(...) → s1_logits
    ├─ sample s1
    ├─ model.decode_s2(context, s1_sample) → s2_logits
    ├─ sample s2
    └─ append to sequence

↓ [Denormalize]
  preds = preds * (std + 1e-5) + mean

↓ Output DataFrame
```

---

## 关键设计考虑

### 1. 两层量化 (s1, s2)
- **s1**：高层特征（快速变化，如价格趋势）
- **s2**：细粒度细节（缓慢变化，如波动）
- 分离优化允许不同的采样策略和损失权重

### 2. 分层嵌入与融合
- 独立嵌入捕捉 s1 和 s2 的不同语义
- 融合投影学习交互

### 3. 依赖感知层
- 通过交叉注意力显式建模 s2 对 s1 的依赖
- 优于隐式依赖（e.g., 级联 logits）

### 4. 自回归生成与采样平均
- 单次采样易陷入局部最优
- 多次采样平均提高稳定性
- 采样策略（temperature, top-k, top-p）控制多样性

### 5. 归一化与裁剪
- Z-score 归一化适应不同幅度的市场
- ±5σ 裁剪异常值防止爆炸
- 反归一化恢复原始单位

### 6. 最大上下文窗口
- Kronos-small/base：max_context = 512
- 长序列自动滑动截断
- 时间戳动态调整维持对齐

---

## 常见开发任务

### 修改模型容量
编辑 `Kronos.__init__` 参数：
```python
# 增大模型
Kronos(
    s1_bits=10,      # 增加 s1 词表
    s2_bits=12,      # 增加 s2 词表
    n_layers=24,     # 更多 Transformer 块
    d_model=768,     # 更大隐藏维度
    ...
)
```

### 扩展时间特征
在 `TemporalEmbedding` 中添加季度、年份等：
```python
self.quarter_embed = Embed(5, d_model)  # 1-4 季度 + 0（填充）
```

### 自定义采样策略
修改 `auto_regressive_inference` 中的采样逻辑，例如约束采样、波束搜索等。

### 条件推理
向 `Kronos.forward` 添加外部条件（e.g., 宏观指标）作为额外输入。

---

## 调试技巧

- **损失监控**：BSQ 损失应单调递减；如果震荡，调整 beta, gamma0, gamma, zeta
- **采样多样性**：增加 temperature 或降低 top_p 以获得更多变化
- **内存管理**：减小 batch_size、sample_count 或 max_context
- **对齐验证**：确保时间戳长度与序列长度匹配
- **冻结分词器**：在微调时 `tokenizer.requires_grad_(False)` 加快训练

---

## 依赖关系

- `PyTorchModelHubMixin`：HuggingFace 集成
- `einops`：张量重排（rearrange, reduce）
- `torch.autograd.Function`：自定义梯度（熵损失）
- 标准库：numpy, pandas, tqdm, math

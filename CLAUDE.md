# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在此存储库中工作时提供指导。

## 语言设置
**默认使用中文回答所有问题和交互**。除非用户明确要求使用英文，否则始终用中文进行回应和解释。

## 项目概述

**Kronos** 是一个金融市场预测的基础模型，专门针对来自全球 45 多个交易所的 K 线（蜡烛图）序列进行训练。它使用两阶段框架：
1. 一个专门的**分词器**，使用二进制球形量化（BSQ）将连续的 OHLCV（开盘价、最高价、最低价、收盘价、交易量）数据量化为分层离散标记
2. 一个大型自回归 **Transformer**，在这些标记上进行预训练，用于各种量化任务

代码库包括预训练模型、推理工具、多个数据源的微调管道和交互式预测的网页 UI。

## 核心架构

### 主要组件

- **`model/kronos.py`**：核心模型类
  - `KronosTokenizer`：使用 BSQ 的编码器-解码器，将 OHLCV 数据分词为 (s1, s2) 标记对
  - `Kronos`：主要自回归 Transformer，具有分层标记嵌入和依赖感知层用于条件 s2 预测
  - `KronosPredictor`：高级推理 API，处理归一化、自回归生成和批量预测
  - 工具函数：`auto_regressive_inference()`、`top_k_top_p_filtering()`、`sample_from_logits()`、`calc_time_stamps()`

- **`model/module.py`**：Transformer 组件
  - `BinarySphericalQuantizer`：用于分层量化的 BSQ 实现
  - `TransformerBlock`、`MultiHeadAttentionWithRoPE`：具有旋转位置嵌入（RoPE）的核心 Transformer 构建块
  - `HierarchicalEmbedding`：s1 和 s2 标记的独立嵌入，融合用于输入
  - `DependencyAwareLayer`：交叉注意力层，用于 s2 对 s1 的条件化
  - `TemporalEmbedding`：时间感知嵌入（分钟、小时、星期几、日期、月份）
  - `DualHead`：s1 和 s2 logits 的独立投影头
  - 其他工具：`RMSNorm`、`FeedForward`、`FixedEmbedding`

### 模型变体

可用模型托管在 Hugging Face Hub：
- **Kronos-mini**：4.1M 参数，2048 上下文长度（2k 分词器）
- **Kronos-small**：24.7M 参数，512 上下文长度（base 分词器）
- **Kronos-base**：102.3M 参数，512 上下文长度（base 分词器）
- **Kronos-large**：499.2M 参数（非开源）

## 微调管道

存储库包括两个微调工作流：

### 1. 基于 Qlib 的微调（`finetune/`）

用于通过 Qlib 在中国 A 股市场数据上训练：
- **`config.py`**：集中式配置（路径、超参数、时间范围、学习率）
- **`qlib_data_preprocess.py`**：从 Qlib 加载，拆分为训练/验证/测试，保存为 pickle 文件
- **`train_tokenizer.py`**：通过 torchrun 使用多 GPU 微调分词器
- **`train_predictor.py`**：在量化标记上微调 Kronos 模型
- **`qlib_test.py`**：使用简单的 top-K 策略对微调后的模型进行回测
- **`dataset.py`**：用于滑动窗口采样的数据集类
- **`utils/`**：用于训练、评估、绘图的辅助函数

**常用命令**：
```bash
# 准备数据
python finetune/qlib_data_preprocess.py

# 训练分词器（多 GPU）
torchrun --standalone --nproc_per_node=NUM_GPUS finetune/train_tokenizer.py

# 训练预测器（多 GPU）
torchrun --standalone --nproc_per_node=NUM_GPUS finetune/train_predictor.py

# 运行回测
python finetune/qlib_test.py --device cuda:0
```

### 2. 基于 CSV 的微调（`finetune_csv/`）

用于在任意 CSV 金融数据上训练（无需 Qlib 依赖）：
- **`config_loader.py`**：基于 YAML 的配置加载和验证
- **`train_sequential.py`**：完整管道（数据加载 → 分词器 → 预测器训练）
- **`finetune_tokenizer.py`**：独立分词器训练
- **`finetune_base_model.py`**：独立预测器训练
- **`configs/`**：示例 YAML 配置文件（例如 `config_ali09988_candle-5min.yaml`）

**常用命令**：
```bash
# 顺序训练（推荐）
python finetune_csv/train_sequential.py --config configs/config_ali09988_candle-5min.yaml

# 跳过现有检查点
python finetune_csv/train_sequential.py --config configs/config_ali09988_candle-5min.yaml --skip-existing

# 单独组件训练
python finetune_csv/finetune_tokenizer.py --config configs/config_ali09988_candle-5min.yaml
python finetune_csv/finetune_base_model.py --config configs/config_ali09988_candle-5min.yaml

# DDP 多 GPU 训练
DIST_BACKEND=nccl torchrun --standalone --nproc_per_node=8 finetune_csv/train_sequential.py --config configs/config_ali09988_candle-5min.yaml
```

## 推理与预测

### 基本用法

```python
from model import Kronos, KronosTokenizer, KronosPredictor
import torch

# 加载模型
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")

# 初始化预测器
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)

# 预测单一序列
pred_df = predictor.predict(
    df=x_df,                    # 历史 OHLCV 数据（lookback_window 行）
    x_timestamp=x_timestamp,    # 历史时间戳
    y_timestamp=y_timestamp,    # 要预测的未来时间戳
    pred_len=pred_len,
    T=1.0,                      # 采样温度
    top_p=0.9,                  # 核采样
    sample_count=1              # 要平均的样本数
)

# 批量预测（并行）
pred_dfs = predictor.predict_batch(
    df_list=[df1, df2, ...],
    x_timestamp_list=[ts1, ts2, ...],
    y_timestamp_list=[ts1, ts2, ...],
    pred_len=pred_len
)
```

**重要**：输入 DataFrame 需要列：`['open', 'high', 'low', 'close']`。volume 和 amount 是可选的（如果缺失则填充零）。

### 示例脚本

- **`examples/prediction_example.py`**：单一序列预测带绘图
- **`examples/prediction_batch_example.py`**：多序列批量预测
- **`examples/prediction_wo_vol_example.py`**：不带 volume/amount 列的预测

## 网页 UI

**`webui/`** 提供交互式预测界面：

```bash
cd webui
python run.py          # 或：python app.py，或：./start.sh
# 访问 http://localhost:7070
```

功能：
- 带智能列检测的 CSV/Feather 数据加载
- 模型选择（mini/small/base）和设备选择（CPU/CUDA/MPS）
- 参数调整：温度、核采样、样本计数
- 固定 400+120 时间窗口滑块
- K 线图可视化和预测叠加
- 与实际数据的对比分析

## 数据与模型管理

### 数据格式要求

**必需列**（区分大小写）：
- `open`、`high`、`low`、`close`：OHLC 价格
- `volume`：交易量（可为 0 或省略）
- `amount`：交易额（可为 0 或省略）
- `timestamps` / `timestamp` / `date`：日期/时间索引

**归一化**：数据自动按序列进行 z-score 归一化（在 ±5σ 处裁剪）。无需预处理。

### Hugging Face 集成

模型使用 `PyTorchModelHubMixin` 从 Hugging Face Hub 无缝加载：
- `.from_pretrained()` / `.save_pretrained()` API
- 自动模型卡和配置持久化
- 支持本地路径和 Hub 标识符

## 训练考虑

- **裁剪**：归一化数据被裁剪到 [-5, 5] 以处理异常值
- **多 GPU**：使用 `torchrun` 和 DDP 进行分布式训练
- **梯度累积**：`accumulation_steps` 参数用于模拟更大的批大小
- **学习率**：分词器的单独学习率（~2e-4）和预测器的学习率（~4e-5）
- **熵损失**：BSQ 包括每个样本和代码簿熵惩罚
- **验证策略**：在验证损失上跟踪最佳模型，保存检查点

## 开发模式

### 自回归推理

模型一次预测一个标记对 (s1, s2)：
1. 使用分词器对历史数据进行编码 → s1 和 s2 标记序列
2. 对每个未来步骤循环：
   - 通过 Kronos 传递 (s1, s2) + 时间戳以获取 s1 logits
   - 从 logits 中采样 s1（使用温度/top-k/top-p 过滤）
   - 在采样的 s1 上条件化，通过依赖感知层传递以获取 s2 logits
   - 从 logits 中采样 s2
   - 追加到序列
3. 使用分词器将最终标记序列解码回 OHLCV

### 批量处理

- `predict_batch()` 堆叠多个序列并并行处理以提高效率
- 所有输入序列必须具有相同的历史和预测长度
- GPU 内存可通过 `self.generate()` 中的较小批大小来管理

## 常见开发任务

### 添加新的微调数据集

1. 准备包含必需列的 CSV（见数据格式要求）
2. 在 `finetune_csv/configs/` 中创建配置 YAML（复制并修改现有配置）
3. 运行：`python finetune_csv/train_sequential.py --config configs/your_config.yaml`

### 扩展模型

`model/` 中的关键扩展点：
- 修改 `TransformerBlock` 以获得不同的注意力机制
- 扩展 `TemporalEmbedding` 以获得其他时间特征
- 更改 `DualHead` 以获得不同的输出分布
- 调整 `HierarchicalEmbedding` 融合策略

### 训练调试

- 检查 `finetune/config.py` 或 YAML 以获取正确的路径和超参数
- 在 `KronosPredictor.predict()` 中使用 `verbose=True` 以查看推理进度
- 监控控制台输出；损失应单调递减
- 由于样本量较小，验证损失可能更嘈杂

## 测试示例

```bash
# 运行预测示例
python examples/prediction_example.py

# 运行批量预测示例
python examples/prediction_batch_example.py

# 检查 CSV 数据上的微调
python finetune_csv/train_sequential.py --config configs/config_ali09988_candle-5min.yaml --help
```

## 系统架构与设计模式

### 整体系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Kronos 金融预测系统架构                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐
│   输入层（Input Layer）
├──────────────────┤
│ • CSV/Feather 数据     │
│ • 金融 K 线数据        │
│ • OHLCV 序列          │
└──────┬───────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│     数据预处理层（Data Preprocessing）        │
├──────────────────────────────────────────────┤
│ • Z-Score 归一化（±5σ 裁剪）                │
│ • 时间戳处理                                 │
│ • 缺失值填充                                 │
│ • 滑动窗口采样（400+120=520 点）            │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│     分词器（Tokenizer Module）               │
├──────────────────────────────────────────────┤
│ ┌─ KronosTokenizer                          │
│ ├─ Encoder:                                 │
│ │  • 输入投影层                             │
│ │  • TransformerBlock × n_enc_layers        │
│ ├─ Binary Spherical Quantizer (BSQ):        │
│ │  • 分层离散化（s1_bits + s2_bits）        │
│ │  • 熵正则化                               │
│ └─ Decoder:                                 │
│    • TransformerBlock × n_dec_layers        │
│    • 输出投影层                             │
└──────┬───────────────────────────────────────┘
       │ (编码) → (s1, s2) 标记对
       │         (每个时间步的离散标记)
       ▼
┌──────────────────────────────────────────────┐
│   核心预测模型（Kronos Transformer）         │
├──────────────────────────────────────────────┤
│ ┌─ 输入嵌入层                               │
│ │  • HierarchicalEmbedding                  │
│ │    - s1 嵌入（vocab_size = 2^s1_bits）   │
│ │    - s2 嵌入（vocab_size = 2^s2_bits）   │
│ │    - 融合投影                             │
│ ├─ 时间嵌入                                 │
│ │  • TemporalEmbedding                      │
│ │    - 分钟、小时、星期几、日期、月份      │
│ ├─ Transformer 堆栈                         │
│ │  • TransformerBlock × n_layers            │
│ │  • MultiHeadAttentionWithRoPE             │
│ │  • FeedForward (SwiGLU)                   │
│ ├─ 标准化层 (RMSNorm)                       │
│ ├─ 依赖感知层 (DependencyAwareLayer)        │
│ │  • 交叉注意力：s2 条件于 s1              │
│ └─ 双头输出                                 │
│    • DualHead:                              │
│      - s1_proj → s1_vocab_logits           │
│      - s2_proj → s2_vocab_logits           │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│   自回归推理引擎（Autoregressive Inference） │
├──────────────────────────────────────────────┤
│ for t in range(pred_len):                  │
│   • 获取当前 (s1, s2) 标记                  │
│   • decode_s1() → s1_logits                │
│   • top_k_top_p_filtering() + 采样         │
│   • decode_s2() → s2_logits (条件于 s1)   │
│   • 采样 s2                                 │
│   • 追加到序列                              │
│   • 保留窗口内最近 max_context 标记        │
└──────┬───────────────────────────────────────┘
       │ (预测的 s1, s2 标记序列)
       ▼
┌──────────────────────────────────────────────┐
│     分词器解码（Tokenizer Decode）           │
├──────────────────────────────────────────────┤
│ • 标记 → 位表示                             │
│ • 双线性解码器                              │
│ • OHLCV 值恢复                              │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│     反归一化与后处理（Denormalization）      │
├──────────────────────────────────────────────┤
│ • 逆 z-score 变换                           │
│ • 时间戳对齐                                 │
│ • DataFrame 格式化                          │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│       输出层（Output & Visualization）       │
├──────────────────────────────────────────────┤
│ • 预测 DataFrame (OHLCV)                   │
│ • K 线图表 (Plotly)                        │
│ • 误差指标 (MAE, RMSE, MAPE)               │
│ • 对比分析                                  │
└──────────────────────────────────────────────┘
```

### 分词器的两阶段量化流程

```
OHLCV 连续数据 (Shape: [Batch, Time, 6])
       │
       ▼
┌─────────────────────────────────────────┐
│  第一阶段：编码（Encoding）              │
├─────────────────────────────────────────┤
│ 输入投影: [B, T, 6] → [B, T, d_model] │
│    ▼                                    │
│ Encoder TransformerBlocks               │
│ (多层自注意力 + 前馈)                   │
│    ▼                                    │
│ 量化嵌入投影: [B, T, d_model]           │
│              → [B, T, codebook_dim]   │
│    ▼                                    │
│ 二进制球形量化 (BSQ):                   │
│ • 量化：x → ±1 (二进制码字)            │
│ • 索引映射：码字 → 整数索引             │
│ • 熵惩罚：保证码簿多样性               │
│    ▼                                    │
│ 量化表示: [B, T, codebook_dim]         │
└─────────────────────────────────────────┘
       │
       ├─ s1_bits: 第一部分 (主要信息)
       │  [B, T, s1_bits] → 索引 (2^s1_bits)
       │
       └─ s2_bits: 第二部分 (细节信息)
          [B, T, s2_bits] → 索引 (2^s2_bits)
       │
       ▼
┌─────────────────────────────────────────┐
│  第二阶段：解码（Decoding）              │
├─────────────────────────────────────────┤
│ 重建量化表示:                            │
│ [B, T, codebook_dim] 从 (s1, s2) 索引  │
│    ▼                                    │
│ 后量化投影 (条件于 s1):                 │
│ [B, T, s1_bits] → [B, T, d_model]     │
│    ▼                                    │
│ Decoder TransformerBlocks               │
│    ▼                                    │
│ 输出投影: [B, T, d_model] → [B, T, 6] │
│    ▼                                    │
│ 重构 OHLCV: (z_pre, z_full)            │
│ • z_pre: 使用 s1 位重建                 │
│ • z_full: 使用完整 (s1+s2) 重建        │
└─────────────────────────────────────────┘
```

### Kronos 主模型的预测流程

```
输入: (s1_ids, s2_ids, timestamps)
     Shape: [B, seq_len]
       │
       ▼
┌─────────────────────────────────────┐
│  1. 分层嵌入                        │
├─────────────────────────────────────┤
│ s1_emb = emb_s1(s1_ids) * √d_model  │
│ s2_emb = emb_s2(s2_ids) * √d_model  │
│ 融合: [s1_emb || s2_emb] → 投影    │
│ x = [B, seq_len, d_model]          │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  2. 时间嵌入相加                    │
├─────────────────────────────────────┤
│ time_emb = TemporalEmbedding(ts)    │
│ x = x + time_emb                    │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  3. Token Dropout                   │
├─────────────────────────────────────┤
│ x = TokenDropout(x)                 │
│ (训练时随机丢弃, 推理时保留)        │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  4. Transformer 堆栈                │
├─────────────────────────────────────┤
│ for layer in transformer_layers:    │
│   x = TransformerBlock(x,           │
│         key_padding_mask)           │
│   • 自注意力 (RoPE)                 │
│   • 残差连接 + LayerNorm            │
│   • FeedForward (SwiGLU)            │
│   [B, seq_len, d_model] → same      │
└─────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────┐
│  5. RMSNorm 标准化                  │
├─────────────────────────────────────┤
│ x = RMSNorm(x)                      │
└─────────────────────────────────────┘
       │
       ├─────────────────────┐
       │                     │
       ▼                     ▼
┌─────────────────┐  ┌──────────────────┐
│  s1 分支        │  │  s2 分支         │
├─────────────────┤  ├──────────────────┤
│ s1_logits =     │  │ 如果训练:        │
│  DualHead(x)    │  │  s1_sampled =    │
│  [B,seq,vocab1] │  │   sample(s1)     │
│                 │  │ 如果推理:        │
│                 │  │  s1_sampled =    │
│                 │  │   argmax(s1)     │
│                 │  │                  │
│                 │  │ s1_emb =         │
│                 │  │  emb_s1(s1_s)    │
│                 │  │                  │
│                 │  │ x2 = DepLayer(x, │
│                 │  │     s1_emb, mask)│
│                 │  │                  │
│                 │  │ s2_logits =      │
│                 │  │  DualHead.s2(x2) │
│                 │  │  [B,seq,vocab2]  │
└─────────────────┘  └──────────────────┘
       │                     │
       └─────────────────────┘
              │
              ▼
输出: (s1_logits, s2_logits)
     Shape: [B, seq_len, vocab_s1/s2]
```

### 自回归推理的时间窗口管理

```
历史数据: [t=0 ... t=399]  (400 点)
预测范围:        [t=400 ... t=519]  (120 点)

时间步 t=0:
┌──────────────────────────────────┐
│ 编码的输入序列                   │
│ [s1_token, s2_token, ...] (400) │
│ 时间戳: [ts_0, ts_1, ..., ts_399]│
│ 最大上下文: 512 点               │
│ 输入长度: 400 ≤ 512 ✓          │
└──────────────────────────────────┘
        │
        ▼
    预测 t=400
    • Kronos.decode_s1() → s1_logits[-1]
    • 采样 s1[400]
    • decode_s2() → s2_logits[-1]
    • 采样 s2[400]
        │
        └─ 追加: [s1_token(400), s2_token(400)]
           新长度: 401

时间步 t=100:
┌──────────────────────────────────┐
│ 编码的输入序列 (已追加 100 步)   │
│ [s1_token, s2_token, ...] (500) │
│ 时间戳: [ts_0, ts_1, ..., ts_499]│
│ 最大上下文: 512 点               │
│ 输入长度: 500 ≤ 512 ✓          │
└──────────────────────────────────┘
        │
        ▼
    预测 t=500

时间步 t=113 (超过上下文):
┌──────────────────────────────────┐
│ 编码的输入序列 (已追加 113 步)   │
│ [s1_token, s2_token, ...] (513) │
│ 时间戳: [ts_113, ts_114,...,ts_512]
│ 最大上下文: 512 点               │
│ 输入长度: 513 > 512 ✗ 截断!    │
│                                  │
│ 截断后: 最后 512 个标记         │
│ [s1_token, s2_token, ...] (512) │
│ 时间戳: [ts_1, ts_2, ..., ts_512]│
└──────────────────────────────────┘
        │
        ▼
    预测 t=513 (从截断后的 512 个标记)
```

### 微调管道架构

```
┌──────────────────────────────────────────────────────────────┐
│                    微调管道 (两阶段)                         │
└──────────────────────────────────────────────────────────────┘

┌─ 阶段 1: 分词器微调 ─────────────────────────────────────┐
│                                                           │
│ 加载预训练分词器:                                        │
│ KronosTokenizer.from_pretrained(base_tokenizer_id)      │
│                    ▼                                     │
│ 数据加载:                                               │
│ • CSV → DataFrame                                       │
│ • 滑动窗口: [400 个历史点 + 标签]                       │
│ • 归一化 + 批次化                                       │
│                    ▼                                     │
│ 微调循环 (每个 epoch):                                   │
│ for batch in train_loader:                             │
│   • x = batch_data                                      │
│   • (z_pre, z), loss_bsq, quantized, indices = tokenizer(x)
│   • 重构损失: MSE(z_pre, x) + MSE(z, x)               │
│   • 量化损失: loss_bsq (BSQ 内部)                      │
│   • 总损失: recon_loss + beta * loss_bsq              │
│   • 反向传播 + 优化器步骤                               │
│                    ▼                                     │
│ 验证:                                                   │
│ • 计算验证 MSE                                         │
│ • 保存最佳检查点                                        │
│                    ▼                                     │
│ 微调的分词器: [base_save_path]/tokenizer/best_model/  │
│                                                           │
└───────────────────────────────────────────────────────────┘

┌─ 阶段 2: 预测器微调 ─────────────────────────────────────┐
│                                                           │
│ 加载预训练 Kronos 和微调分词器:                          │
│ model = Kronos.from_pretrained(base_model_id)          │
│ tokenizer = KronosTokenizer(fine_tuned_ckpt)           │
│                    ▼                                     │
│ 冻结分词器参数（可选）:                                 │
│ for param in tokenizer.parameters():                   │
│   param.requires_grad = False                          │
│                    ▼                                     │
│ 数据加载 (使用分词器编码):                              │
│ for x, y in dataloader:                               │
│   x_tokens = tokenizer.encode(x)    # (s1, s2)        │
│   y_tokens = tokenizer.encode(y)    # (s1, s2)        │
│   x_tokens = [s1_ids, s2_ids]                         │
│                    ▼                                     │
│ 微调循环 (每个 epoch):                                   │
│ for batch in train_loader:                             │
│   s1_ids, s2_ids, timestamps = batch                   │
│   # 训练时使用 teacher forcing                          │
│   s1_logits, s2_logits = model(s1_ids, s2_ids,       │
│                                timestamps,             │
│                                use_teacher_forcing)    │
│   # 计算损失                                           │
│   ce_s1 = CrossEntropy(s1_logits, s1_target_ids)     │
│   ce_s2 = CrossEntropy(s2_logits, s2_target_ids)     │
│   总损失 = (ce_s1 + ce_s2) / 2                       │
│   # 反向传播                                          │
│   loss.backward()                                      │
│   optimizer.step()                                     │
│                    ▼                                     │
│ 验证 + 回测:                                            │
│ • 评估验证集 (自回归推理)                               │
│ • 计算预测误差                                         │
│ • 简单 top-K 策略回测                                  │
│ • 保存最佳检查点                                       │
│                    ▼                                     │
│ 微调的预测器: [base_save_path]/basemodel/best_model/ │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### 设计模式应用

#### 1. **工厂模式 (Factory Pattern)**
```python
# 在 model/__init__.py 中
model_dict = {
    'kronos_tokenizer': KronosTokenizer,
    'kronos': Kronos,
    'kronos_predictor': KronosPredictor
}

def get_model_class(model_name):
    """根据名称获取模型类"""
    if model_name in model_dict:
        return model_dict[model_name]
    else:
        raise NotImplementedError
```

#### 2. **适配器模式 (Adapter Pattern)**
```python
# KronosPredictor 作为适配器
# - 适配底层 Kronos 模型和 KronosTokenizer
# - 为用户提供统一的高级 API (predict, predict_batch)
# - 处理数据流转和格式转换
```

#### 3. **构建者模式 (Builder Pattern)**
```python
# KronosPredictor 的初始化
predictor = KronosPredictor(
    model=model,
    tokenizer=tokenizer,
    device="cuda:0",
    max_context=512,
    clip=5
)
# 逐步构建预测器配置
```

#### 4. **策略模式 (Strategy Pattern)**
```python
# 采样策略
def sample_from_logits(logits, temperature, top_k, top_p):
    """不同采样策略的组合"""
    # 策略 1: 温度缩放
    # 策略 2: top-k 过滤
    # 策略 3: top-p (核采样) 过滤
```

#### 5. **模板方法模式 (Template Method)**
```python
# 预测流程模板
def predict(self, df, x_timestamp, y_timestamp, pred_len, ...):
    """预测流程的标准模板"""
    1. 数据验证
    2. 数据归一化
    3. 调用生成器
    4. 反归一化
    5. 返回结果
```

### 关键数据流转示意

```
用户输入 DataFrame
(历史 OHLCV 数据, 时间戳)
       │
       ▼
┌─────────────────────────┐
│ 数据校验 & 预处理        │
│ • 检查必需列             │
│ • 处理时间戳             │
│ • 填充缺失的 vol/amt    │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 统计计算                 │
│ • 均值、标准差           │
│ • 用于归一化             │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ Z-Score 归一化           │
│ x_norm = (x - μ) / σ   │
│ clip 到 [-5, 5]        │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 张量转换                 │
│ numpy → PyTorch        │
│ 添加 batch 维度         │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 分词器编码               │
│ OHLCV → (s1, s2) 标记  │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 自回归推理               │
│ (已在流程图中详细说明)   │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 分词器解码               │
│ (s1, s2) 标记 → OHLCV  │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 反归一化                 │
│ x = x_norm * σ + μ     │
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│ 后处理                   │
│ • 转换回 numpy          │
│ • DataFrame 格式化      │
│ • 添加时间戳索引        │
└─────┬───────────────────┘
      │
      ▼
输出预测 DataFrame (OHLCV)
```

## 重要说明

- **AI 生成的注释**：`finetune/` 中的代码具有 AI 生成的文档字符串（Gemini 2.5 Pro）；将代码视为真实来源
- **上下文长度**：Kronos-small 和 Kronos-base 的最大上下文为 512；如果输入更长，会自动截断
- **配置中无秘密**：对 API 密钥（例如 Comet ML 凭证）使用环境变量
- **时间对齐**：确保 x_timestamp 和 y_timestamp 与 DataFrame 索引正确对齐

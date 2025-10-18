# Finetune 模块代码逻辑详解

## 概述

`finetune` 模块提供了基于 **Qlib** 的完整微调管道，用于在中国 A 股市场数据上微调 Kronos 模型。支持 DDP 分布式训练、Comet ML 实验跟踪、以及集成的回测功能。

### 核心特性
- ✅ Qlib 数据自动加载与预处理
- ✅ 两阶段顺序训练（分词器 → 预测器）
- ✅ 分布式训练支持（DDP、多 GPU）
- ✅ Comet ML 实验跟踪与监控
- ✅ 集成回测系统（基于 Qlib）
- ✅ 时间序列数据随机采样
- ✅ 自动最佳模型保存

---

## 文件结构与职责

```
finetune/
├── config.py                  # 统一配置管理
├── dataset.py                 # QlibDataset - 数据加载类
├── qlib_data_preprocess.py    # 数据预处理（Qlib 数据加载与分割）
├── train_tokenizer.py         # 分词器 DDP 训练脚本
├── train_predictor.py         # 预测器 DDP 训练脚本
├── qlib_test.py               # 推理与回测逻辑
└── utils/
    ├── __init__.py
    └── training_utils.py      # DDP 和训练工具函数
```

---

## 1. config.py - 统一配置管理

### 1.1 Config 类

**职责**：集中管理所有配置参数，包括数据路径、训练超参数、模型路径、回测参数等。

**初始化流程**：
```
Config()
├─ 数据参数（qlib_data_path, lookback_window, predict_window 等）
├─ 数据集分割参数（train_time_range, val_time_range, test_time_range）
├─ 训练超参数（epochs, batch_size, learning_rate 等）
├─ 模型路径（预训练模型、保存目录）
├─ 实验配置（Comet ML、日志）
└─ 回测参数（持仓数、阈值、推理采样策略）
```

**关键属性**：

| 类别 | 属性 | 默认值 | 说明 |
|------|------|--------|------|
| **Qlib 数据** | qlib_data_path | `~/.qlib/qlib_data/cn_data` | Qlib 数据目录 |
| | instrument | `'csi300'` | 指数代码（csi300/csi800/csi1000） |
| | dataset_begin_time | `"2011-01-01"` | 数据加载起始日期 |
| | dataset_end_time | `'2025-06-05'` | 数据加载结束日期 |
| **窗口参数** | lookback_window | 90 | 历史数据窗口长度 |
| | predict_window | 10 | 预测窗口长度 |
| | max_context | 512 | 模型最大上下文长度 |
| **特征** | feature_list | `['open', 'high', 'low', 'close', 'vol', 'amt']` | 主要特征 |
| | time_feature_list | `['minute', 'hour', 'weekday', 'day', 'month']` | 时间特征 |
| **数据划分** | train_time_range | `["2011-01-01", "2022-12-31"]` | 训练集时间范围 |
| | val_time_range | `["2022-09-01", "2024-06-30"]` | 验证集时间范围 |
| | test_time_range | `["2024-04-01", "2025-06-05"]` | 测试集时间范围 |
| **训练** | epochs | 30 | 训练轮数 |
| | batch_size | 50 | 单 GPU 批次大小 |
| | n_train_iter | 100,000 | 每轮训练迭代数 |
| | n_val_iter | 20,000 | 每轮验证迭代数 |
| | tokenizer_learning_rate | 2e-4 | 分词器学习率 |
| | predictor_learning_rate | 4e-5 | 预测器学习率 |
| **回测** | backtest_n_symbol_hold | 50 | 持仓股票数 |
| | backtest_hold_thresh | 5 | 最小持仓周期 |
| | inference_T | 0.6 | 推理温度 |
| | inference_top_p | 0.9 | 核采样 p 值 |
| | inference_sample_count | 5 | 采样次数 |

---

## 2. qlib_data_preprocess.py - 数据预处理

### 2.1 QlibDataPreprocessor 类

**职责**：从 Qlib 加载原始金融数据，进行预处理，并按时间划分为 train/val/test 数据集。

**工作流程**：

```
QlibDataPreprocessor()
    ↓
initialize_qlib()
    └─ qlib.init(provider_uri, region=REG_CN)
    ↓
load_qlib_data()
    ├─ 从 Qlib 日历中确定加载范围
    ├─ 使用 QlibDataLoader 加载原始数据
    ├─ 逐符号处理：
    │  ├─ 枢纽表格重塑（多索引 → 特征列）
    │  ├─ 重命名特征（$open → open）
    │  ├─ 计算衍生特征（amt = 4均价 × vol）
    │  └─ 前向填充 NaN
    └─ 存储为 self.data[symbol] = DataFrame
    ↓
prepare_dataset()
    ├─ 按时间范围划分
    ├─ 创建掩码：train_mask, val_mask, test_mask
    ├─ 提取对应时间段数据
    └─ 保存 pickle 文件：
       ├─ train_data.pkl
       ├─ val_data.pkl
       └─ test_data.pkl
```

**使用方法**：
```bash
python qlib_data_preprocess.py
```

**输出结构**：
```
./data/processed_datasets/
├── train_data.pkl    # {symbol: DataFrame, ...}
├── val_data.pkl
└── test_data.pkl
```

---

## 3. dataset.py - 数据集加载

### 3.1 QlibDataset 类

**职责**：将预处理后的 pickle 数据加载到 PyTorch Dataset 中，支持随机采样和分布式训练。

**初始化流程**：

```python
QlibDataset(data_type='train')
    ├─ 加载 pickle 文件
    ├─ 提取符号列表
    ├─ 预计算所有有效窗口的 (symbol, start_idx) 对
    │  └─ 有效起点数 = len(df) - window + 1（确保有足够样本）
    └─ n_samples = min(config.n_train_iter, len(indices))
```

**关键方法**：

| 方法 | 功能 |
|------|------|
| `set_epoch_seed(epoch)` | 为分布式采样器设置 epoch 种子 |
| `__len__()` | 返回数据集大小（n_samples） |
| `__getitem__(idx)` | 随机采样一个窗口 |

**采样机制**（核心特性）：
```python
def __getitem__(self, idx):
    # 注意：idx 参数被忽略！
    # 使用专用 RNG 从所有可用索引中随机抽取
    random_idx = self.py_rng.randint(0, len(self.indices) - 1)
    symbol, start_idx = self.indices[random_idx]

    # 提取窗口
    window = data[symbol].iloc[start_idx:start_idx+window_size]

    # 归一化
    x = normalize_and_clip(window[features])
    x_stamp = window[time_features]

    return x_tensor, x_stamp_tensor
```

**特性**：
- 实例级别归一化（per-sample z-score）
- 样本级独立 mean/std
- 数据裁剪到 ±5σ
- 独立 RNG 不干扰其他随机过程

---

## 4. train_tokenizer.py - 分词器训练

### 4.1 架构

```
main(config)
    ↓
setup_ddp()  # 初始化分布式环境
    ├─ dist.init_process_group(backend="nccl")
    └─ 设置 CUDA 设备
    ↓
create_dataloaders(config, rank, world_size)
    ├─ QlibDataset('train')
    ├─ QlibDataset('val')
    └─ DistributedSampler
    ↓
train_model(model, device, config, ...)
    ├─ 优化器：AdamW (lr=2e-4, weight_decay=0.1)
    ├─ 学习率调度：OneCycleLR (pct_start=3%)
    └─ 30 轮循环
       ├─ 训练批处理
       ├─ 梯度累积
       ├─ 优化器步长
       ├─ 验证循环
       └─ all_reduce 聚合损失
    ↓
cleanup_ddp()  # 清理分布式环境
```

### 4.2 训练循环

**前向传播**：
```python
# 批处理
ori_batch_x (B, T, 6)  # OHLCV

# 梯度累积
for j in range(accumulation_steps):
    # 分割批次
    batch_x = ori_batch_x[start:end]

    # 前向传播
    zs, bsq_loss, _, _ = model(batch_x)
    z_pre, z = zs

    # 损失计算
    recon_loss_pre = MSE(z_pre, batch_x)
    recon_loss_all = MSE(z, batch_x)
    recon_loss = recon_loss_pre + recon_loss_all
    loss = (recon_loss + bsq_loss) / 2

    # 缩放反向传播
    loss_scaled = loss / accumulation_steps
    loss_scaled.backward()

# 梯度同步（自动在 DDP 中）
torch.nn.utils.clip_grad_norm_(model, max_norm=2.0)
optimizer.step()
scheduler.step()
```

**验证循环**：
```python
model.eval()
with torch.no_grad():
    for batch_x in val_loader:
        zs, _, _, _ = model(batch_x)
        _, z = zs
        val_loss += MSE(z, batch_x)

# all_reduce 聚合各进程的验证损失
dist.all_reduce(val_loss_tensor)
avg_val_loss = val_loss_sum / val_count  # 全局平均
```

### 4.3 命令与日志

**启动命令**：
```bash
# 单 GPU
python train_tokenizer.py

# 多 GPU（8 卡）
torchrun --standalone --nproc_per_node=8 train_tokenizer.py
```

**日志记录**：
- 每 100 步：训练损失、VQ 损失、重建损失、学习率
- 每轮末：验证损失、轮耗时、最佳模型保存
- Comet ML：自动上传所有指标和检查点

---

## 5. train_predictor.py - 预测器训练

### 5.1 核心流程

**前向传播**：
```python
# 输入
batch_x (B, T, 6)          # OHLCV 特征
batch_x_stamp (B, T, 5)    # 时间特征

# 编码为标记
with torch.no_grad():
    token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)

# 自回归准备
token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]    # 输入标记
token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]    # 目标标记

# 前向传播
logits = model(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
# 输出: (s1_logits, s2_logits)

# 损失计算
loss, s1_loss, s2_loss = model.head.compute_loss(
    logits[0], logits[1],
    token_out[0], token_out[1]
)
# 损失 = (CE(s1) + CE(s2)) / 2
```

**优化参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| 学习率 | 4e-5 | 相对较低，稳定性优于高速 |
| Betas | (0.9, 0.95) | 动量和二阶矩系数 |
| Weight Decay | 0.1 | L2 正则化 |
| 梯度裁剪 | max_norm=3.0 | 防止梯度爆炸 |
| 调度器 | OneCycleLR | 分段学习率调整 |

---

## 6. qlib_test.py - 推理与回测

### 6.1 QlibTestDataset

**职责**：为推理提供测试数据，生成元数据（符号、时间戳）。

```python
class QlibTestDataset(Dataset):
    def __getitem__(self, idx):
        # 顺序访问（不随机）
        symbol, start_idx, timestamp = self.indices[idx]

        # 分离历史和预测窗口
        context_df = df[start_idx:context_end]
        predict_df = df[context_end:predict_end]

        x = context_df[features]         # (lookback, 6)
        x_stamp = context_df[time_feat]  # (lookback, 5)
        y_stamp = predict_df[time_feat]  # (predict, 5)

        return x_tensor, x_stamp, y_stamp, symbol, timestamp
```

### 6.2 推理流程

```python
generate_predictions(config, test_data)
    ├─ load_models() → KronosTokenizer, Kronos
    ├─ 创建 QlibTestDataset
    ├─ 批量推理循环
    │  ├─ auto_regressive_inference()
    │  │  ├─ 编码历史 → 标记
    │  │  ├─ 逐步生成预测标记
    │  │  └─ 解码为 OHLCV
    │  ├─ 计算信号（与最后一日收盘的差价）
    │  │  ├─ 'last': 最后一日预测
    │  │  ├─ 'mean': 预测期平均
    │  │  ├─ 'max': 预测期最高
    │  │  └─ 'min': 预测期最低
    │  └─ 堆叠结果
    └─ 转为 DataFrame（datetime 索引，symbol 列）
```

### 6.3 回测逻辑

```python
class QlibBacktest:
    def run_single_backtest(signal_series):
        # 策略：TopkDropoutStrategy
        # - 每日选择 top-50 高分股票
        # - 最小持仓 5 天
        # - 交易成本：0.1% 开仓 + 0.15% 平仓

        strategy = TopkDropoutStrategy(
            topk=50, n_drop=5, hold_thresh=5, signal=signal_series
        )

        portfolio_metric, _ = backtest(
            strategy=strategy,
            start_time='2024-07-01',
            end_time='2025-06-05',
            account=100M,
            benchmark='SH000300'  # CSI-300
        )

        # 分析：收益率、夏普比率、最大回撤等
        analysis = risk_analysis(returns, freq='day')

        return report_df  # 累计收益、成本等
```

**使用方法**：
```python
backtester = QlibBacktest(config)
backtester.run_and_plot_results(model_preds)
# 输出：累计收益曲线、超额收益、对比基准
```

---

## 7. utils/training_utils.py - 工具函数

### 关键函数

| 函数 | 功能 |
|------|------|
| `setup_ddp()` | 初始化 DDP 环境，返回 (rank, world_size, local_rank) |
| `cleanup_ddp()` | 销毁进程组 |
| `set_seed(seed, rank)` | 设置全局随机种子（rank 偏移确保多进程不重复） |
| `get_model_size(model)` | 计算参数量并格式化（B/M/K） |
| `reduce_tensor(tensor, world_size, op)` | 跨进程同步张量（SUM/AVG） |
| `format_time(seconds)` | 秒数转 H:M:S 字符串 |

---

## 8. 完整工作流

### 8.1 第一次运行（从原始数据开始）

```bash
# 步骤 1：数据预处理（仅需一次）
python qlib_data_preprocess.py
# 输出：train_data.pkl, val_data.pkl, test_data.pkl

# 步骤 2：训练分词器（多 GPU）
torchrun --standalone --nproc_per_node=8 train_tokenizer.py
# 输出：outputs/models/finetune_tokenizer_demo/checkpoints/best_model/

# 步骤 3：训练预测器（多 GPU）
torchrun --standalone --nproc_per_node=8 train_predictor.py
# 输出：outputs/models/finetune_predictor_demo/checkpoints/best_model/

# 步骤 4：推理与回测
python -c "from qlib_test import main; main()"
# 输出：predictions.pkl, backtest_result_example.png
```

### 8.2 目录结构（训练后）

```
outputs/
├── models/
│   ├── finetune_tokenizer_demo/
│   │   ├── checkpoints/
│   │   │   └── best_model/
│   │   │       ├── config.json
│   │   │       └── pytorch_model.bin
│   │   └── summary.json
│   └── finetune_predictor_demo/
│       ├── checkpoints/
│       │   └── best_model/
│       │       ├── config.json
│       │       └── pytorch_model.bin
│       └── summary.json
└── backtest_results/
    └── finetune_backtest_demo/
        ├── predictions.pkl
        └── backtest_result_example.png

data/
└── processed_datasets/
    ├── train_data.pkl
    ├── val_data.pkl
    └── test_data.pkl
```

---

## 9. DDP 分布式训练详解

### 9.1 启动机制

```bash
torchrun --standalone --nproc_per_node=8 train_tokenizer.py

# 等效于：
# 启动 8 个进程，分别执行相同的脚本
# 自动设置环境变量：
#   RANK=0,1,2,...,7
#   WORLD_SIZE=8
#   LOCAL_RANK=0,1,2,...,7
#   MASTER_ADDR=localhost
#   MASTER_PORT=29500
```

### 9.2 进程内同步

```python
# 每个 GPU 进程独立执行
[Rank 0] 读取数据 → 前向 → 反向 → 梯度
[Rank 1] 读取数据 → 前向 → 反向 → 梯度
         ...
[Rank 7] 读取数据 → 前向 → 反向 → 梯度

    ↓ DDP 自动同步梯度 ↓

所有进程的梯度平均 → 优化器步长 → 权重更新

    ↓ dist.barrier() 同步点 ↓

所有进程等待，确保完成
```

### 9.3 数据并行策略

```python
# DistributedSampler 自动分片
train_sampler = DistributedSampler(
    train_dataset,
    num_replicas=8,    # 8 卡
    rank=rank,         # 当前卡号 0-7
    shuffle=True
)

# 每卡处理不重叠的样本子集
Rank 0: indices [0, 8, 16, 24, ...]
Rank 1: indices [1, 9, 17, 25, ...]
...
```

---

## 10. 调试与优化

### 10.1 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| CUDA OOM | 批次过大 | 减小 batch_size、启用梯度累积 |
| DDP 挂起 | 进程不同步 | 检查 dist.barrier()、等待时间 |
| 数据加载慢 | num_workers 不足 | 增加 num_workers（默认 2） |
| 损失 NaN | 学习率过高 | 降低 learning_rate、启用梯度裁剪 |
| 模型不收敛 | 超参数不适配 | 尝试 lr 调度器、降低初始 lr |

### 10.2 性能优化

| 技术 | 效果 | 成本 |
|------|------|------|
| DDP 多 GPU | ~8x 加速（8 卡） | 需要多 GPU |
| 梯度累积 | 稳定性 + 内存效率 | 轻度减速 |
| 混合精度 | 加速 + 内存节省 | 精度降低 |
| Pin Memory | 数据传输加速 | 内存占用 |

**推荐配置**：
```python
config.batch_size = 50           # 单 GPU
config.accumulation_steps = 1    # 有效批次 = 50 * 8 = 400
config.num_workers = 4           # 异步加载
```

---

## 11. 模型使用

训练完成后，使用微调模型进行推理：

```python
from model import Kronos, KronosTokenizer, KronosPredictor

# 加载微调模型
tokenizer = KronosTokenizer.from_pretrained(
    "outputs/models/finetune_tokenizer_demo/checkpoints/best_model"
)
model = Kronos.from_pretrained(
    "outputs/models/finetune_predictor_demo/checkpoints/best_model"
)

# 初始化预测器
predictor = KronosPredictor(model, tokenizer, device="cuda:0")

# 预测
pred_df = predictor.predict(
    df=historical_ohlcv,
    x_timestamp=x_ts,
    y_timestamp=y_ts,
    pred_len=10
)
```

---

## 12. 与 finetune_csv 的对比

| 特性 | finetune | finetune_csv |
|------|----------|--------------|
| **数据源** | Qlib (A股) | 任意 CSV |
| **数据加载** | Qlib API | CSV 读取 |
| **配置方式** | Python Config 类 | YAML 文件 |
| **回测** | 集成 Qlib 回测 | 不包含 |
| **分布式** | torchrun | YAML + CLI |
| **灵活性** | 固定流程 | 更灵活 |
| **易用性** | 需要 Qlib 配置 | 开箱即用 |

---

## 总结

`finetune` 模块通过紧密集成 Qlib 和 Kronos，提供了：
- 🔄 **完整的 A 股数据管道**：从原始数据到预测
- 🚀 **高效的分布式训练**：DDP 多 GPU 加速
- 📊 **内置回测系统**：快速评估策略效果
- 🔍 **详细的日志和监控**：Comet ML 集成
- 🛠️ **生产级代码质量**：完善的错误处理和验证

通过配置 `Config` 类的参数，可以快速适配不同的市场数据和模型配置，进行大规模微调实验。

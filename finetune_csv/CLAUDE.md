# Finetune_CSV 模块代码逻辑详解

## 概述

`finetune_csv` 模块提供了一套完整的微调管道，用于在任意 CSV 格式的金融数据上对 Kronos 模型进行微调。无需 Qlib 依赖，支持单 GPU、多 GPU (DDP) 训练。

### 核心特性
- ✅ 基于 YAML 配置的灵活管道
- ✅ 两阶段顺序训练：分词器 → 预测器
- ✅ 分布式训练支持 (DDP、多 GPU)
- ✅ 自动数据划分 (train/val/test)
- ✅ 预训练模型加载或随机初始化
- ✅ 日志系统与模型保存

---

## 文件结构与职责

```
finetune_csv/
├── config_loader.py           # 配置加载与管理
├── finetune_tokenizer.py      # 分词器微调训练脚本
├── finetune_base_model.py     # 预测器微调训练脚本 + 数据集类
├── train_sequential.py        # 顺序协调器（推荐使用）
└── configs/
    └── config_ali09988_candle-5min.yaml  # 示例配置
```

---

## 1. config_loader.py - 配置管理

### 1.1 ConfigLoader 类

**职责**：加载、解析并管理 YAML 配置文件。

**关键方法**：

| 方法 | 功能 |
|------|------|
| `__init__(config_path)` | 加载 YAML 配置，解析动态路径 |
| `_load_config()` | 读取 YAML 并验证文件存在 |
| `_resolve_dynamic_paths(config)` | 处理路径模板变量（如 `{exp_name}`） |
| `get(key, default)` | 嵌套字典访问，支持点号分割路径 |
| `get_*_config()` | 提取特定配置段（data/training/model_paths 等） |
| `update_config(updates)` | 递归更新配置字典 |
| `save_config(save_path)` | 保存配置到 YAML 文件 |
| `print_config()` | 打印完整配置 |

**路径解析示例**：
```yaml
model_paths:
  exp_name: "ali_v1"
  base_path: "/data/models"
  base_save_path: ""  # 会被解析为 "/data/models/ali_v1"
  finetuned_tokenizer: ""  # 会被解析为 "/data/models/ali_v1/tokenizer/best_model"
```

**嵌套访问示例**：
```python
config.get('training.batch_size')  # 自动分割并逐层访问
```

---

### 1.2 CustomFinetuneConfig 类

**职责**：整合所有配置段，生成训练所需的完整配置对象。

**初始化流程**：
```
ConfigLoader(config_path)
    ↓
_load_all_configs()  # 提取所有配置段
    ├─ data_config (lookback_window, predict_window, train_ratio 等)
    ├─ training_config (epochs, batch_size, learning_rate 等)
    ├─ model_paths (保存路径、预训练模型路径)
    ├─ experiment_config (实验名称、是否训练分词器/预测器)
    ├─ device_config (使用 CUDA、设备 ID)
    └─ distributed_config (DDP 后端)
    ↓
_compute_full_paths()  # 计算完整路径
    ├─ tokenizer_save_path
    ├─ tokenizer_best_model_path
    ├─ basemodel_save_path
    └─ basemodel_best_model_path
```

**关键属性**：

| 类别 | 属性 | 默认值 | 说明 |
|------|------|--------|------|
| **数据** | lookback_window | 512 | 历史窗口长度 |
| | predict_window | 48 | 预测窗口长度 |
| | max_context | 512 | 模型最大上下文 |
| | clip | 5.0 | 数据裁剪范围 ±5σ |
| | train_ratio | 0.9 | 训练集比例 |
| **训练** | tokenizer_epochs | 30 | 分词器训练轮数 |
| | basemodel_epochs | 30 | 预测器训练轮数 |
| | batch_size | 160 | 批次大小 |
| | tokenizer_learning_rate | 2e-4 | 分词器学习率 |
| | predictor_learning_rate | 4e-5 | 预测器学习率 |
| | adam_weight_decay | 0.1 | AdamW 权重衰减 |
| **模型** | pre_trained_tokenizer | True | 使用预训练分词器 |
| | pre_trained_predictor | True | 使用预训练预测器 |
| | skip_existing | False | 跳过已有模型 |

**方法**：

| 方法 | 功能 |
|------|------|
| `get_tokenizer_config()` | 返回分词器训练所需配置字典 |
| `get_basemodel_config()` | 返回预测器训练所需配置字典 |
| `print_config_summary()` | 打印配置摘要 |

---

## 2. finetune_tokenizer.py - 分词器微调

### 2.1 数据加载与辅助函数

| 函数 | 功能 |
|------|------|
| `set_seed(seed, rank)` | 设置随机种子（CPU/GPU），保证可复现性 |
| `get_model_size(model)` | 获取模型参数量并格式化（M/B/K） |
| `format_time(seconds)` | 秒数转时间字符串 |
| `setup_logging(exp_name, log_dir, rank)` | 配置日志系统（控制台 + 文件） |
| `create_dataloaders(config)` | 创建训练/验证数据加载器 |

**数据加载器流程**：
```
CustomKlineDataset (由 finetune_base_model.py 定义)
    ↓
分为 train/val 两个数据集
    ↓
DistributedSampler (如果使用 DDP)
    ↓
DataLoader (num_workers=6, pin_memory=True)
```

---

### 2.2 train_tokenizer() 函数

**职责**：主训练循环，优化分词器参数。

**关键流程**：

```python
def train_tokenizer(model, device, config, save_dir, logger):
```

**前向传播**：
```
batch_x (B, T, 6) OHLCV 数据
    ↓
KronosTokenizer.forward(batch_x)
    ├─ z_pre:  (B, T, 6) - 预部分重建
    ├─ z:      (B, T, 6) - 全部分重建
    ├─ bsq_loss: 标量 - 量化损失
    └─ indices: 量化索引
    ↓
损失计算：
    recon_loss_pre = MSE(z_pre, batch_x)
    recon_loss_all = MSE(z, batch_x)
    recon_loss = recon_loss_pre + recon_loss_all
    loss = (recon_loss + bsq_loss) / 2
```

**优化策略**：

| 技术 | 实现 |
|------|------|
| **优化器** | AdamW (lr=2e-4, weight_decay=0.1) |
| **学习率调度** | OneCycleLR (pct_start=3%, epochs=30) |
| **梯度累积** | 支持 accumulation_steps（模拟更大批次） |
| **梯度裁剪** | max_norm=2.0 防止爆炸 |
| **验证策略** | 每轮记录最佳模型（基于验证损失） |

**分布式训练**：
- 自动检测 DDP 环境变量 (RANK, WORLD_SIZE, LOCAL_RANK)
- 使用 DDP 包装模型，all_reduce 验证损失
- 仅 rank=0 保存模型和日志

**日志记录**：
```
每 50 步：Loss、VQ_Loss、Recon_Loss_Pre/All、学习率
每轮末：验证损失、轮耗时、最佳模型保存路径
```

---

## 3. finetune_base_model.py - 预测器微调

### 3.1 CustomKlineDataset 类

**职责**：加载 CSV 数据，进行滑动窗口采样，生成训练样本。

**初始化参数**：
```python
CustomKlineDataset(
    data_path='data.csv',
    data_type='train',           # 'train', 'val', 'test'
    lookback_window=512,         # 历史长度
    predict_window=48,           # 预测长度（实际未用）
    clip=5.0,                    # 数据裁剪范围
    seed=100,                    # 随机种子
    train_ratio=0.7,             # 训练集比例
    val_ratio=0.15,
    test_ratio=0.15
)
```

**工作流程**：

```
CSV 文件 (timestamps, open, high, low, close, volume, amount)
    ↓
_load_and_preprocess_data()
    ├─ 按 timestamps 排序
    ├─ 提取时间特征 (minute, hour, weekday, day, month)
    └─ 前向填充 NaN 值
    ↓
_split_data_by_time()
    └─ 按时间顺序划分：train[:90%] | val[90%:] 或 test[105%:]
    ↓
__getitem__(idx) 采样
    ├─ 计算随机起点（确定性采样用于复现）
    ├─ 提取 [lookback_window, predict_window, 1] 长度窗口
    ├─ Z-score 归一化
    ├─ 裁剪到 ±5σ
    └─ 返回 (x_tensor, x_stamp_tensor)
```

**样本构成**：
```
返回值：(x_tensor, x_stamp_tensor)
x_tensor      (window, 6)       # [open, high, low, close, volume, amount]
x_stamp_tensor (window, 5)      # [minute, hour, weekday, day, month]
```

**数据集大小**：
```python
n_samples = len(data) - window + 1
# 例：data_len=2000, window=561 → 1440 samples
```

**epoch 支持**：
- `set_epoch_seed(epoch)` 用于分布式采样器同步
- 训练时使用伪随机采样以提高多样性
- 验证/测试时顺序采样确保一致性

---

### 3.2 train_model() 函数

**职责**：主训练循环，优化预测器参数。

**前向传播**：
```python
# 编码历史数据到标记
token_seq_0, token_seq_1 = tokenizer.encode(batch_x, half=True)

# 分离输入和目标（自回归）
token_in = [token_seq_0[:, :-1], token_seq_1[:, :-1]]
token_out = [token_seq_0[:, 1:], token_seq_1[:, 1:]]

# 预测
logits = model(token_in[0], token_in[1], batch_x_stamp[:, :-1, :])
# logits: (s1_logits, s2_logits)

# 损失
loss, s1_loss, s2_loss = model.head.compute_loss(
    logits[0], logits[1],
    token_out[0], token_out[1]
)
```

**损失定义**：
```python
ce_s1 = CrossEntropy(s1_logits, s1_targets)
ce_s2 = CrossEntropy(s2_logits, s2_targets)
loss = (ce_s1 + ce_s2) / 2
```

**优化策略**：

| 技术 | 实现 |
|------|------|
| **优化器** | AdamW (lr=4e-5, betas=(0.9, 0.95), weight_decay=0.1) |
| **学习率调度** | OneCycleLR (pct_start=3%, epochs=30) |
| **梯度裁剪** | max_norm=3.0 |
| **验证策略** | 每轮记录最佳模型 |

---

### 3.3 关键优化

**DDP 支持**：
- 跨 GPU 同步梯度
- all_reduce 聚合训练和验证损失
- 仅主进程保存模型

**数据并行**：
```python
use_ddp = dist.is_available() and dist.is_initialized()
train_loader = DataLoader(..., sampler=train_sampler if use_ddp else None)
```

---

## 4. train_sequential.py - 顺序协调器

### 4.1 SequentialTrainer 类

**职责**：协调两阶段训练，统一的高级 API。

**初始化**：
```python
trainer = SequentialTrainer(config_path='config.yaml')
```

**内部状态**：
- `self.config`：完整配置对象
- `self.rank`, `self.world_size`, `self.local_rank`：DDP 信息
- `self.device`：计算设备

**关键方法**：

| 方法 | 功能 |
|------|------|
| `_setup_device()` | 设置 CUDA/CPU 设备 |
| `_setup_distributed()` | 初始化 DDP 进程组 |
| `_check_existing_models()` | 检查模型是否已存在 |
| `_create_directories()` | 创建保存目录 |
| `train_tokenizer_phase()` | 执行分词器微调 |
| `train_basemodel_phase()` | 执行预测器微调 |
| `run_training()` | 完整训练流程 |

**工作流程**：

```
SequentialTrainer.__init__()
    ↓
_setup_distributed()
    ├─ 初始化 DDP (如果 world_size > 1)
    └─ 设置后端 (nccl / gloo)
    ↓
_create_directories()
    ├─ tokenizer_save_path
    └─ basemodel_save_path
    ↓
train_tokenizer_phase()
    ├─ 检查 skip_existing
    ├─ 加载预训练或随机初始化
    ├─ 调用 finetune_tokenizer.train_tokenizer()
    └─ 保存最佳模型到 tokenizer_best_model_path
    ↓
train_basemodel_phase()
    ├─ 加载微调后的分词器
    ├─ 加载预训练或随机初始化预测器
    ├─ 调用 finetune_base_model.train_model()
    └─ 保存最佳模型到 basemodel_best_model_path
    ↓
输出总耗时和模型路径
```

### 4.2 命令行接口

```python
python train_sequential.py --config configs/config_ali09988_candle-5min.yaml
```

**可选参数**：

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径（默认 config.yaml） |
| `--skip-tokenizer` | 跳过分词器训练 |
| `--skip-basemodel` | 跳过预测器训练 |
| `--skip-existing` | 跳过已存在的模型 |

**DDP 多 GPU 使用**：
```bash
DIST_BACKEND=nccl torchrun --standalone --nproc_per_node=8 train_sequential.py --config configs/config.yaml
```

---

## 5. 数据流完整示例

### 5.1 单 GPU 训练流程

```bash
# 1. 准备配置文件
cp configs/config_ali09988_candle-5min.yaml configs/my_config.yaml
# 编辑 data_path, model_paths 等

# 2. 运行顺序训练
python train_sequential.py --config configs/my_config.yaml

# 内部流程：
# ├─ 加载配置
# ├─ 分词器微调
# │  ├─ 加载数据 (lookback=512, predict=48)
# │  ├─ 30 轮训练
# │  └─ 保存到 base_save_path/tokenizer/best_model
# ├─ 预测器微调
# │  ├─ 加载微调分词器
# │  ├─ 数据编码为标记对
# │  ├─ 30 轮标记预测训练
# │  └─ 保存到 base_save_path/basemodel/best_model
# └─ 输出完成信息
```

### 5.2 多 GPU 训练流程

```bash
# 8 卡 DDP 训练
DIST_BACKEND=nccl torchrun --standalone --nproc_per_node=8 train_sequential.py --config configs/my_config.yaml

# 内部流程：
# ├─ 每 GPU 初始化为单独进程（rank 0-7）
# ├─ DDP 初始化 (NCCL 后端)
# ├─ 数据分布到各 GPU
# ├─ 各 GPU 独立前向 + 后向，同步梯度
# ├─ 仅 rank=0 保存模型
# └─ 同步点：dist.barrier() 确保所有 GPU 完成
```

---

## 6. YAML 配置文件格式

### 示例配置：config_ali09988_candle-5min.yaml

```yaml
# 数据配置
data:
  data_path: "./data/ali09988_candle-5min.csv"
  lookback_window: 512      # 历史窗口
  predict_window: 48        # 预测窗口长度
  max_context: 512          # 模型最大上下文
  clip: 5.0                 # 数据裁剪范围
  train_ratio: 0.7
  val_ratio: 0.15
  test_ratio: 0.15

# 训练配置
training:
  tokenizer_epochs: 30
  basemodel_epochs: 30
  batch_size: 160
  log_interval: 50
  num_workers: 6
  seed: 100
  tokenizer_learning_rate: 2e-4
  predictor_learning_rate: 4e-5
  adam_beta1: 0.9
  adam_beta2: 0.95
  adam_weight_decay: 0.1
  accumulation_steps: 1

# 模型路径
model_paths:
  exp_name: "ali09988_5min_v1"
  base_path: "./output"
  base_save_path: ""  # 自动为 output/ali09988_5min_v1
  pretrained_tokenizer: "NeoQuasar/Kronos-Tokenizer-base"
  pretrained_predictor: "NeoQuasar/Kronos-small"
  tokenizer_save_name: "tokenizer"
  basemodel_save_name: "basemodel"

# 实验配置
experiment:
  name: "Kronos_Finetune_Ali09988"
  description: "Finetune on Ali09988 5min candlestick data"
  use_comet: false
  train_tokenizer: true
  train_basemodel: true
  skip_existing: false
  pre_trained_tokenizer: true
  pre_trained_predictor: true

# 设备配置
device:
  use_cuda: true
  device_id: 0

# 分布式配置
distributed:
  use_ddp: false
  backend: "nccl"
```

---

## 7. 常见工作流

### 7.1 微调预训练模型（推荐）

```bash
python train_sequential.py --config configs/my_config.yaml
```

配置中设置：
```yaml
experiment:
  pre_trained_tokenizer: true   # ✓ 使用预训练
  pre_trained_predictor: true   # ✓ 使用预训练
```

### 7.2 从随机初始化训练

配置中设置：
```yaml
experiment:
  pre_trained_tokenizer: false  # 随机初始化
  pre_trained_predictor: false  # 随机初始化
model_paths:
  pretrained_tokenizer: "path/to/tokenizer/config.json"  # 用于读取架构
  pretrained_predictor: "path/to/predictor/config.json"  # 用于读取架构
```

### 7.3 仅训练分词器

```bash
python train_sequential.py --config configs/my_config.yaml --skip-basemodel
```

### 7.4 跳过已训练的组件

```bash
python train_sequential.py --config configs/my_config.yaml --skip-existing
```

---

## 8. 输出与保存结构

```
output/
└── ali09988_5min_v1/          # exp_name
    ├── tokenizer/
    │   ├── best_model/        # ✓ 最佳分词器检查点
    │   │   ├── config.json
    │   │   └── pytorch_model.bin
    │   └── checkpoints/       # 其他检查点
    ├── basemodel/
    │   ├── best_model/        # ✓ 最佳预测器检查点
    │   │   ├── config.json
    │   │   └── pytorch_model.bin
    │   └── checkpoints/
    └── logs/
        ├── tokenizer_training_rank_0.log
        ├── basemodel_training_rank_0.log
        └── ...
```

---

## 9. 调试与故障排查

### 问题 1：数据加载错误
```
FileNotFoundError: config file not found
```
**解决**：检查 data_path 是否正确，文件是否包含必需列。

### 问题 2：CUDA 内存不足
```
RuntimeError: CUDA out of memory
```
**解决**：
- 减小 batch_size
- 减小 lookback_window
- 增加 accumulation_steps 并减小实际批次

### 问题 3：DDP 同步问题
```
RuntimeError: NCCL operation timed out
```
**解决**：
- 检查各 GPU 是否同时启动
- 确保 world_size 与实际 GPU 数匹配
- 增加 timeout 时间

### 问题 4：模型不收敛
```
损失持续上升或震荡
```
**解决**：
- 降低学习率 (tokenizer_learning_rate / predictor_learning_rate)
- 检查数据是否正确归一化
- 增加训练轮数

---

## 10. 性能优化建议

| 优化策略 | 效果 | 成本 |
|---------|------|------|
| **梯度累积** | 模拟更大批次，稳定训练 | 轻度减速 |
| **混合精度** | 减小内存，加快计算 | 精度降低 |
| **DDP 多 GPU** | 线性加速 | 需要多 GPU |
| **num_workers** | 异步数据加载 | CPU 占用 |
| **pin_memory** | 加快数据到 GPU 传输 | 内存占用 |

**推荐设置**：
```yaml
training:
  batch_size: 160          # 单 GPU
  num_workers: 6           # 根据 CPU 核心数调整
  accumulation_steps: 2    # 有效批次 = 160 * 2 = 320
```

---

## 11. 接下来的步骤

训练完成后，使用 `KronosPredictor` 进行推理：

```python
from model import Kronos, KronosTokenizer, KronosPredictor

tokenizer = KronosTokenizer.from_pretrained("output/ali09988_5min_v1/tokenizer/best_model")
model = Kronos.from_pretrained("output/ali09988_5min_v1/basemodel/best_model")
predictor = KronosPredictor(model, tokenizer, device="cuda:0")

# 单序列预测
pred_df = predictor.predict(
    df=historical_data,
    x_timestamp=x_ts,
    y_timestamp=y_ts,
    pred_len=48
)
```

---

## 总结

`finetune_csv` 模块通过模块化设计和配置驱动的方法，提供了：
- 🔄 **灵活的两阶段管道**：分词器 + 预测器独立优化
- 📊 **完整的数据支持**：无需 Qlib，任意 CSV 数据
- 🚀 **分布式训练**：轻松扩展到多 GPU
- 📝 **详细的日志和检查点管理**
- 🎯 **自动的最佳模型选择**：基于验证损失

通过合理配置和调整超参数，可以在定制数据集上快速微调 Kronos 模型以获得最佳性能。

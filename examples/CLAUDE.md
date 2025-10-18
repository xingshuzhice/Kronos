# Examples 模块代码逻辑详解

## 概述

`examples` 模块提供了三个实用的示例脚本，展示了如何使用 Kronos 模型进行单序列预测、批量预测以及无成交量数据的预测。这些示例可以作为快速入门的参考。

### 核心示例
- ✅ `prediction_example.py` - 单序列预测（完整 OHLCVA 特征）
- ✅ `prediction_batch_example.py` - 批量并行预测
- ✅ `prediction_wo_vol_example.py` - 仅用价格数据预测（无成交量）

---

## 1. prediction_example.py - 单序列预测

### 1.1 使用场景

**适用于**：
- 单支股票的时间序列预测
- 快速验证模型功能
- 学习基本使用流程

**输入**：历史 K 线数据 (400 条)
**输出**：未来 120 条时间步的预测 OHLCVA

### 1.2 完整工作流程

```python
# ========================================
# 步骤 1：加载模型和分词器
# ========================================
from model import Kronos, KronosTokenizer, KronosPredictor

tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
```

**说明**：
- 从 Hugging Face Hub 自动下载预训练模型
- `Kronos-Tokenizer-base`：基础分词器，支持 512 上下文长度
- `Kronos-small`：小型预测器，24.7M 参数

```python
# ========================================
# 步骤 2：初始化预测器
# ========================================
predictor = KronosPredictor(
    model,
    tokenizer,
    device="cuda:0",      # GPU 设备
    max_context=512       # 最大上下文窗口
)
```

**参数**：
- `device="cuda:0"`：在 GPU 上执行推理（更快）
- `max_context=512`：限制输入序列长度（默认值）
- 可选 `clip=5`：数据裁剪范围（±5σ）

```python
# ========================================
# 步骤 3：准备数据
# ========================================
import pandas as pd

# 加载 CSV 数据
df = pd.read_csv("./data/XSHG_5min_600977.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

# 定义窗口
lookback = 400         # 历史数据长度
pred_len = 120         # 预测长度

# 提取历史数据
x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
x_timestamp = df.loc[:lookback-1, 'timestamps']

# 提取目标时间戳
y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']
```

**数据要求**：
- 必需列：`['open', 'high', 'low', 'close']`（OHLC）
- 可选列：`volume`、`amount`（缺失时填 0）
- 时间戳：任意时间格式（需转换为 pandas 时间类型）

**数据形状**：
```
x_df:       (400, 6)    # 历史数据
x_timestamp: (400,)     # 历史时间戳
y_timestamp: (120,)     # 预测时间戳（不与历史重叠）
```

```python
# ========================================
# 步骤 4：执行预测
# ========================================
pred_df = predictor.predict(
    df=x_df,                    # 历史 OHLCVA 数据
    x_timestamp=x_timestamp,    # 历史时间戳
    y_timestamp=y_timestamp,    # 未来时间戳
    pred_len=pred_len,          # 预测长度（通常 = len(y_timestamp)）
    T=1.0,                      # 采样温度（1.0 = 标准）
    top_p=0.9,                  # 核采样 p 值（0.9 = 保留 90% 累计概率）
    sample_count=1,             # 采样次数（> 1 时多次采样并平均）
    verbose=True                # 打印进度
)
```

**参数说明**：

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `T` | 1.0 | [0.1, 2.0] | 低 T（如 0.5）= 更确定的预测；高 T（如 1.5）= 更多样化 |
| `top_p` | 0.9 | [0.5, 1.0] | 核采样，过滤低概率标记，保持多样性 |
| `top_k` | 0 | ≥0 | Top-k 过滤（0 = 不使用） |
| `sample_count` | 1 | ≥1 | 多次采样并平均，提高稳定性 |
| `verbose` | True | - | 打印推理进度条 |

**输出形状**：
```
pred_df: (120, 6)  # 预测的 OHLCVA 数据
         columns: ['open', 'high', 'low', 'close', 'volume', 'amount']
         index: y_timestamp
```

```python
# ========================================
# 步骤 5：可视化结果
# ========================================
def plot_prediction(kline_df, pred_df):
    """绘制预测结果与真实数据的对比图"""

    # 对齐时间戳
    pred_df.index = kline_df.index[-pred_df.shape[0]:]

    # 提取收盘价和成交量
    sr_close = kline_df['close']
    sr_pred_close = pred_df['close']
    sr_volume = kline_df['volume']
    sr_pred_volume = pred_df['volume']

    # 创建图表
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    # 收盘价对比
    ax1.plot(sr_close, label='Ground Truth', color='blue', linewidth=1.5)
    ax1.plot(sr_pred_close, label='Prediction', color='red', linewidth=1.5)
    ax1.set_ylabel('Close Price')
    ax1.legend()
    ax1.grid(True)

    # 成交量对比
    ax2.plot(sr_volume, label='Ground Truth', color='blue', linewidth=1.5)
    ax2.plot(sr_pred_volume, label='Prediction', color='red', linewidth=1.5)
    ax2.set_ylabel('Volume')
    ax2.legend()
    ax2.grid(True)

    plt.tight_layout()
    plt.show()

# 合并历史和预测数据
kline_df = df.loc[:lookback+pred_len-1]
plot_prediction(kline_df, pred_df)
```

### 1.3 完整运行示例

```bash
cd examples/
python prediction_example.py
```

**预期输出**：
```
Forecasted Data Head:
            open       high        low      close      volume      amount
2024-01-15  100.50   101.20   100.30    100.95      1000000   101000000
2024-01-16  100.95   101.50   100.80    101.20      1100000   111200000
...
```

然后显示对比图表：
- 上图：收盘价对比（蓝线=真实，红线=预测）
- 下图：成交量对比

---

## 2. prediction_batch_example.py - 批量预测

### 2.1 使用场景

**适用于**：
- 多支股票同时预测
- 提高 GPU 利用率（批量处理更高效）
- 大规模回测场景

**输入**：N 个历史序列的列表
**输出**：N 个预测结果的列表

### 2.2 工作流程

```python
import pandas as pd
from model import Kronos, KronosTokenizer, KronosPredictor

# 加载模型
tokenizer = KronosTokenizer.from_pretrained('path/to/tokenizer')
model = Kronos.from_pretrained("path/to/model")
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)

# 准备多个序列
df = pd.read_csv("./data/XSHG_5min_600977.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

lookback = 400
pred_len = 120

# 准备 5 个预测任务
dfs = []
xtsp = []
ytsp = []

for i in range(5):
    # 每个序列的数据窗口不重叠
    start_idx = i * 400
    end_idx = i * 400 + lookback

    idf = df.loc[start_idx:end_idx-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
    i_x_timestamp = df.loc[start_idx:end_idx-1, 'timestamps']
    i_y_timestamp = df.loc[end_idx:end_idx+pred_len-1, 'timestamps']

    dfs.append(idf)
    xtsp.append(i_x_timestamp)
    ytsp.append(i_y_timestamp)
```

**数据准备要点**：
- 所有序列必须有相同的**历史长度**（lookback = 400）
- 所有序列必须有相同的**预测长度**（pred_len = 120）
- 时间戳列表要与 DataFrame 列表对应

```python
# ========================================
# 批量预测
# ========================================
pred_dfs = predictor.predict_batch(
    df_list=dfs,              # N 个 DataFrame
    x_timestamp_list=xtsp,    # N 个历史时间戳
    y_timestamp_list=ytsp,    # N 个未来时间戳
    pred_len=pred_len,        # 预测长度
    T=1.0,                    # 采样温度
    top_p=0.9,                # 核采样
    sample_count=1,           # 采样次数
    verbose=True              # 打印进度
)
```

**关键参数**：
- `df_list`：所有序列必须长度相同
- `x_timestamp_list`、`y_timestamp_list`：列表中元素顺序必须对应
- 返回值：与输入顺序相同的预测 DataFrame 列表

**返回结构**：
```python
pred_dfs  # 列表，长度 = 5
pred_dfs[0]  # (120, 6) DataFrame，对应第一个序列
pred_dfs[1]  # (120, 6) DataFrame，对应第二个序列
...
```

### 2.3 性能提升

**单个预测 vs 批量预测**：

| 操作 | 时间（相对） | GPU 利用率 |
|------|-------------|-----------|
| 单序列 × 5 次 | 5× | ~30% |
| 批量预测 × 1 次 | 1.5× | ~90% |
| **加速倍数** | **3.3×** | 更高效 |

**最佳实践**：
- 批处理尽可能多序列（受 GPU 内存限制）
- 建议批大小：50-200 个序列

---

## 3. prediction_wo_vol_example.py - 无成交量预测

### 3.1 使用场景

**适用于**：
- 缺少成交量数据的市场（如期货、外汇）
- 仅有价格数据的情景
- 简化输入的演示

**输入**：历史价格数据（仅 OHLC，无 volume/amount）
**输出**：预测价格

### 3.2 工作流程

```python
import pandas as pd
from model import Kronos, KronosTokenizer, KronosPredictor

# 模型加载（同步骤 1）
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)

# 数据准备（仅包含 OHLC，无 volume/amount）
df = pd.read_csv("./data/XSHG_5min_600977.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

lookback = 400
pred_len = 120

# 关键区别：仅提取价格列
x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close']]
x_timestamp = df.loc[:lookback-1, 'timestamps']
y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']
```

**与完整示例的区别**：
```python
# 完整版
x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]

# 无成交量版
x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close']]
```

```python
# ========================================
# 预测（完全相同的 API）
# ========================================
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=1.0,
    top_p=0.9,
    sample_count=1,
    verbose=True
)
```

**重要**：
- 模型会自动检测缺失列并填 0
- 输出仍然包含 6 列（volume/amount = 0）
- 预测质量可能略低（成交量信息缺失）

```python
# ========================================
# 可视化（仅显示价格）
# ========================================
def plot_prediction(kline_df, pred_df):
    """简化版：仅绘制收盘价"""
    pred_df.index = kline_df.index[-pred_df.shape[0]:]

    sr_close = kline_df['close']
    sr_pred_close = pred_df['close']

    fig, ax = plt.subplots(1, 1, figsize=(8, 4))
    ax.plot(sr_close, label='Ground Truth', color='blue', linewidth=1.5)
    ax.plot(sr_pred_close, label='Prediction', color='red', linewidth=1.5)
    ax.set_ylabel('Close Price')
    ax.legend()
    ax.grid(True)

    plt.tight_layout()
    plt.show()

kline_df = df.loc[:lookback+pred_len-1]
plot_prediction(kline_df, pred_df)
```

---

## 4. 常见任务和代码片段

### 4.1 调整预测参数

```python
# 保守预测（较少多样性）
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=0.5,        # ↓ 低温度 = 更确定
    top_p=0.7,    # ↓ 低 p 值 = 限制多样性
    sample_count=1
)

# 探索性预测（高多样性）
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=1.5,        # ↑ 高温度 = 更随机
    top_p=1.0,    # ↑ 高 p 值 = 允许低概率选择
    sample_count=5  # ↑ 多次采样并平均
)
```

### 4.2 处理不同的数据源

```python
# 从 numpy 数组创建 DataFrame
import numpy as np

data = np.random.rand(400, 6) * 100  # 随机价格数据
x_df = pd.DataFrame(
    data,
    columns=['open', 'high', 'low', 'close', 'volume', 'amount']
)
x_timestamp = pd.date_range(start='2024-01-01', periods=400, freq='5min')
y_timestamp = pd.date_range(start='2024-01-01', periods=120, freq='5min',
                            offset=pd.Timedelta(minutes=2000))

pred_df = predictor.predict(x_df, x_timestamp, y_timestamp, pred_len=120)
```

### 4.3 保存和加载预测结果

```python
# 保存预测
pred_df.to_csv('./predictions.csv')

# 加载预测
loaded_pred = pd.read_csv('./predictions.csv', index_col=0, parse_dates=True)

# 保存为 pickle（保留索引）
import pickle
with open('./predictions.pkl', 'wb') as f:
    pickle.dump(pred_df, f)

# 加载
with open('./predictions.pkl', 'rb') as f:
    pred_df = pickle.load(f)
```

### 4.4 批量预测到数据库

```python
# 预测多支股票
symbols = ['600977', '600000', '601988']
results = {}

for symbol in symbols:
    df = pd.read_csv(f"./data/XSHG_5min_{symbol}.csv")
    df['timestamps'] = pd.to_datetime(df['timestamps'])

    x_df = df.loc[:lookback-1, ['open', 'high', 'low', 'close', 'volume', 'amount']]
    x_timestamp = df.loc[:lookback-1, 'timestamps']
    y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']

    pred_df = predictor.predict(x_df, x_timestamp, y_timestamp, pred_len)
    results[symbol] = pred_df

# 保存所有结果
for symbol, pred_df in results.items():
    pred_df.to_csv(f'./predictions_{symbol}.csv')
```

---

## 5. 数据格式规范

### 5.1 输入数据格式

**必需列**（区分大小写）：
```
['open', 'high', 'low', 'close']  # 必需
['volume', 'amount']              # 可选（缺失自动填 0）
```

**有效的 DataFrame 示例**：
```python
df = pd.DataFrame({
    'open':   [100.0, 100.5, 100.3, ...],
    'high':   [101.0, 101.2, 101.0, ...],
    'low':    [99.8,  100.0, 100.1, ...],
    'close':  [100.5, 100.3, 100.8, ...],
    'volume': [1000000, 1100000, 950000, ...],
    'amount': [101000000, 110000000, ...],
    'timestamps': [pd.Timestamp(...), ...]
})
```

### 5.2 时间戳格式

```python
# 有效的时间戳格式
x_timestamp = pd.to_datetime(['2024-01-01', '2024-01-02', ...])
x_timestamp = pd.date_range(start='2024-01-01', periods=400, freq='5min')
x_timestamp = pd.DatetimeIndex(['2024-01-01 09:30', '2024-01-01 09:35', ...])

# 无效（会报错）
x_timestamp = ['2024-01-01', '2024-01-02']  # 字符串列表
x_timestamp = [datetime.datetime(...), ...]  # datetime 对象（需转换）
```

### 5.3 数据验证

```python
# 检查必需列
required_cols = ['open', 'high', 'low', 'close']
assert all(col in df.columns for col in required_cols), "缺少必需列"

# 检查数据范围
assert df[required_cols].isnull().sum().sum() == 0, "存在 NaN 值"
assert (df[required_cols] > 0).all().all(), "价格应为正数"

# 检查时间戳
assert len(x_timestamp) == len(x_df), "时间戳和数据长度不匹配"
assert isinstance(x_timestamp, pd.DatetimeIndex), "时间戳需为 DatetimeIndex"
```

---

## 6. 故障排查

### 问题 1：CUDA 内存不足

```python
# 错误信息
RuntimeError: CUDA out of memory
```

**解决方案**：
```python
# 方案 1：使用 CPU
predictor = KronosPredictor(model, tokenizer, device="cpu")

# 方案 2：减小采样次数
pred_df = predictor.predict(..., sample_count=1)  # 改为 1 而不是 5

# 方案 3：缩小上下文窗口
predictor = KronosPredictor(model, tokenizer, max_context=256)
```

### 问题 2：列名不匹配

```python
# 错误信息
ValueError: Price columns ['open', 'high', 'low', 'close'] not found in DataFrame
```

**解决方案**：
```python
# 检查和重命名列
print(df.columns)  # 查看实际列名
df = df.rename(columns={
    'Open': 'open',
    'High': 'high',
    'Low': 'low',
    'Close': 'close'
})
```

### 问题 3：时间戳对齐

```python
# 错误信息
Warning: x_timestamp 和 y_timestamp 有重叠
```

**解决方案**：
```python
# 确保不重叠
lookback = 400
pred_len = 120

x_timestamp = df.loc[:lookback-1, 'timestamps']       # 0:400
y_timestamp = df.loc[lookback:lookback+pred_len-1, 'timestamps']  # 400:520
# 注意：y_timestamp 从 400 开始，不与 x_timestamp 重叠
```

---

## 7. 性能优化建议

| 优化技巧 | 效果 | 成本 |
|---------|------|------|
| 使用 GPU | ~10× 加速 | 需要 GPU |
| 批量预测 | ~3× 加速 | 需要相同大小序列 |
| 减少采样次数 | 快速预测 | 质量下降 |
| 降低温度 | 更快收敛 | 多样性减少 |

**推荐设置**：
```python
# 生产环境
predictor = KronosPredictor(model, tokenizer, device="cuda:0", max_context=512)
pred_df = predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=1.0,
    top_p=0.9,
    sample_count=3,  # 平衡速度和质量
    verbose=False    # 关闭进度输出
)

# 批量预测（多个序列）
pred_dfs = predictor.predict_batch(
    df_list=dfs,
    x_timestamp_list=xtsp,
    y_timestamp_list=ytsp,
    pred_len=pred_len,
    sample_count=1,  # 批处理已经并行化
    verbose=True
)
```

---

## 总结

三个示例脚本涵盖了 Kronos 模型的主要使用场景：

1. **prediction_example.py**：基础用法，适合快速了解
2. **prediction_batch_example.py**：高效的大规模预测
3. **prediction_wo_vol_example.py**：处理不完整数据

**核心 API**：
```python
# 单序列
pred_df = predictor.predict(df, x_ts, y_ts, pred_len, ...)

# 批量
pred_dfs = predictor.predict_batch(df_list, x_ts_list, y_ts_list, pred_len, ...)
```

通过调整采样参数（T、top_p、sample_count），可以灵活控制预测的多样性和确定性，以适应不同的应用场景。

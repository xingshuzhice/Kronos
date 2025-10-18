# Kronos 模型功能分析：WebUI 中缺失的功能

## 概述

本文档对比了 **Kronos 模型层面实现的完整功能** 与 **WebUI 中实际展现和使用的功能**，识别出 WebUI 中还没有体现的模型能力。

---

## 1. 模型层面实现的完整功能清单

### 1.1 KronosTokenizer 类功能

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| ✅ **forward()** | kronos.py:74 | 完整的编码-量化-解码流程 |
| ✅ **encode()** | kronos.py:142 | 仅编码，返回量化索引 (s1, s2) |
| ✅ **decode()** | kronos.py:161 | 仅解码，从索引恢复原始数据 |
| ✅ **indices_to_bits()** | kronos.py:115 | 量化索引转双极位表示 (-1, 1) |
| ❌ **量化统计** | - | 缺失：量化损失统计、码簿使用率 |
| ❌ **编码可视化** | - | 缺失：量化过程可视化 |

### 1.2 Kronos 主模型功能

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| ✅ **forward()** | kronos.py:239 | s1/s2 联合预测，支持 teacher forcing |
| ✅ **decode_s1()** | kronos.py:278 | 仅 s1 标记预测 |
| ✅ **decode_s2()** | kronos.py:310 | 条件化 s2 预测（依赖 s1） |
| ❌ **仅解码模式** | - | 缺失：纯推理优化（无梯度） |
| ❌ **混合精度推理** | - | 缺失：FP16/INT8 量化推理 |
| ❌ **批处理优化** | - | 缺失：动态批处理、KV 缓存 |
| ❌ **序列截断策略** | - | 缺失：智能上下文管理 |

### 1.3 采样和推理功能

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| ✅ **top_k_top_p_filtering()** | kronos.py:331 | Top-K 和核采样过滤 |
| ✅ **sample_from_logits()** | kronos.py:373 | 从 logits 中采样 |
| ✅ **auto_regressive_inference()** | kronos.py:389 | 自回归逐步生成预测 |
| ✅ **calc_time_stamps()** | kronos.py:446 | 时间戳提取 |
| ❌ **采样策略对比** | - | 缺失：多种采样方法对比（beam search、top-a 等） |
| ❌ **早停策略** | - | 缺失：预测不确定度高时自动停止 |
| ❌ **动态温度调整** | - | 缺失：基于预测难度的温度自适应 |
| ❌ **推理加速** | - | 缺失：投机解码、草稿模型加速 |

### 1.4 KronosPredictor 高级功能

| 功能 | 实现位置 | 说明 |
|------|---------|------|
| ✅ **predict()** | kronos.py:483 | 单序列预测 |
| ✅ **predict_batch()** | kronos.py:526 | 批量预测 |
| ✅ **generate()** | kronos.py:472 | 张量化推理 |
| ✅ **数据标准化** | kronos.py:500+ | Z-score 归一化 |
| ✅ **采样平均** | kronos.py:515+ | 多次采样平均 |
| ❌ **不确定度估计** | - | 缺失：预测置信度、方差估计 |
| ❌ **异常检测** | - | 缺失：预测异常值检测 |
| ❌ **对比学习** | - | 缺失：相似序列检索 |
| ❌ **概率分布** | - | 缺失：返回分布而非点估计 |
| ❌ **Streaming 推理** | - | 缺失：流式处理长序列 |

---

## 2. WebUI 中实际使用的功能

### 2.1 WebUI 使用的模型功能

```python
# app.py 中的实际使用
predictor.predict(
    df=x_df,
    x_timestamp=x_timestamp,
    y_timestamp=y_timestamp,
    pred_len=pred_len,
    T=temperature,          # 温度参数
    top_p=top_p,           # 核采样参数
    sample_count=sample_count  # 采样次数
)
```

### 2.2 WebUI 中使用的参数

| 参数 | 范围 | WebUI 中使用 |
|------|------|------------|
| temperature (T) | 0.1 - 2.0 | ✅ 完整支持 |
| top_p | 0.1 - 1.0 | ✅ 完整支持 |
| sample_count | 1 - 5 | ✅ 完整支持 |
| top_k | 0+ | ❌ 未暴露 |
| device | cpu/cuda/mps | ✅ 完整支持 |

### 2.3 WebUI 中缺失展现的功能

| 功能 | 模型是否支持 | WebUI 状态 | 优先级 |
|------|------------|---------|--------|
| **编码-量化过程** | ✅ 支持 | ❌ 不展示 | 🟡 中 |
| **Top-K 采样** | ✅ 支持 | ❌ 未暴露 | 🟢 低 |
| **采样多样性控制** | ✅ 支持 | ⚠️ 部分 | 🟡 中 |
| **不确定度估计** | ❌ 无 | ❌ 无 | 🔴 高 |
| **批量预测** | ✅ 支持 | ❌ 不使用 | 🔴 高 |
| **采样策略对比** | ❌ 无 | ❌ 无 | 🔴 高 |
| **混合精度推理** | ❌ 无 | ❌ 无 | 🟡 中 |
| **推理性能监控** | ❌ 无 | ❌ 无 | 🟡 中 |
| **预测后处理** | ❌ 无 | ❌ 无 | 🟡 中 |

---

## 3. WebUI 中应该添加的模型功能

### 🔴 优先级高 - 强烈建议立即实现

#### 3.1 批量预测优化
**模型能力**：`predict_batch()` 支持批处理

**当前状态**：WebUI 仅使用 `predict()` 单个预测

**建议实现**：
- ✅ 在 webui 中启用 `predict_batch()`
- ✅ 支持多个序列并行预测
- ✅ 性能对比（单次 vs 批量）

```python
# 模型支持批量预测
results = predictor.predict_batch(
    df_list=[df1, df2, df3],
    x_timestamp_list=[ts1, ts2, ts3],
    y_timestamp_list=[ys1, ys2, ys3],
    pred_len=120,
    T=1.0,
    top_p=0.9,
    sample_count=1
)
```

**WebUI 中的体现方式**：
- 多文件并行预测界面
- 进度条显示
- 性能统计（耗时对比）

---

#### 3.2 不确定度估计（模型需要扩展）
**模型能力**：暂未实现

**建议新增**：
- 多次采样的方差估计
- 预测置信度区间
- 异常预测检测

**实现方式**：
```python
# 建议在模型中扩展
def predict_with_uncertainty(self, df, x_timestamp, y_timestamp, pred_len,
                            num_samples=10, confidence=0.95):
    """预测含不确定度"""

    predictions = []
    for _ in range(num_samples):
        # 多次采样
        pred = self.predict(df, x_timestamp, y_timestamp, pred_len,
                           T=1.2, top_p=0.9, sample_count=1)
        predictions.append(pred)

    # 计算统计信息
    pred_mean = np.mean(predictions, axis=0)
    pred_std = np.std(predictions, axis=0)

    # 构建置信区间
    z_score = norm.ppf((1 + confidence) / 2)
    ci_lower = pred_mean - z_score * pred_std
    ci_upper = pred_mean + z_score * pred_std

    return {
        'prediction': pred_mean,
        'std': pred_std,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper
    }
```

**WebUI 中的体现方式**：
- 预测区间可视化（置信带）
- 不确定度热力图
- 高风险预测警告

---

#### 3.3 采样策略对比（模型已支持，WebUI 需要）
**模型能力**：已支持多种采样（top-k、top-p）

**当前状态**：WebUI 仅暴露 top-p，隐藏 top-k

**建议实现**：
- Top-K 采样参数暴露
- 多种采样策略对比
- 采样多样性指标

```python
# 模型已支持但 WebUI 未使用
def sample_from_logits(logits, temperature=1.0, top_k=None, top_p=None):
    """
    支持三种采样方式：
    1. top_k: 只从概率最高的 K 个标记中采样
    2. top_p (nucleus sampling): 从累积概率达 P 的最小集合采样
    3. 混合: top_k + top_p
    """
```

**WebUI 中的体现方式**：
```
采样策略选择器：
┌─────────────────────┐
│ 采样模式选择        │
├─────────────────────┤
│ ○ 贪心 (Greedy)    │
│ ○ Top-K 采样       │  → K 值滑块
│ ● Top-P 采样       │  → P 值滑块 (当前使用)
│ ○ Top-K + Top-P    │  → K 值 + P 值
│ ○ 温度采样         │  → T 值滑块
└─────────────────────┘

对比展示：
同一数据，不同采样策略的预测对比
```

---

#### 3.4 采样多样性分析
**模型能力**：多次采样已支持

**当前状态**：WebUI 支持 sample_count，但无分析

**建议实现**：
- 采样一致性分析
- 预测多样性指标
- 采样稳定性检测

```python
# 新增分析功能
def analyze_sampling_diversity(predictions_list):
    """分析采样多样性"""

    # 采样间的差异
    pairwise_distances = []
    for i in range(len(predictions_list)):
        for j in range(i+1, len(predictions_list)):
            dist = np.mean(np.abs(predictions_list[i] - predictions_list[j]))
            pairwise_distances.append(dist)

    mean_distance = np.mean(pairwise_distances)

    # 预测方向一致性
    directions = np.sign(np.diff(predictions_list, axis=1))
    direction_agreement = np.mean([np.mean(d == directions[0]) for d in directions])

    return {
        'diversity': mean_distance,
        'direction_agreement': direction_agreement,
        'stable': direction_agreement > 0.8
    }
```

**WebUI 中的体现方式**：
- 采样置信度评分
- 多采样预测带（显示采样范围）
- "采样稳定性" 指标

---

### 🟡 优先级中 - 建议后续实现

#### 3.5 编码-量化过程可视化
**模型能力**：Tokenizer 支持 encode/decode

**当前状态**：完全黑盒，无可视化

**建议实现**：
```python
# 新增可视化接口
def visualize_quantization(self, x):
    """
    返回量化过程的中间表示：
    - 原始数据
    - 编码后的连续表示
    - 量化后的离散索引
    - 解码后的重建数据
    - 重建误差
    """
    z_pre, z = self.forward(x)
    s1_indices, s2_indices = self.encode(x, half=True)
    x_recon = self.decode([s1_indices, s2_indices], half=True)

    return {
        'original': x,
        'quantized_indices': (s1_indices, s2_indices),
        'reconstructed': x_recon,
        'reconstruction_error': x - x_recon
    }
```

**WebUI 中的体现方式**：
- 原始数据 → 量化编码 → 重建数据对比图
- 量化损失分布图
- 码簿使用率热力图

---

#### 3.6 推理性能监控面板
**模型能力**：支持所有，需封装

**当前状态**：无性能统计

**建议实现**：
```python
# 新增性能追踪
class PerformanceProfiler:
    def profile_prediction(self, predictor, x, x_stamp, y_stamp, pred_len):
        """
        记录预测过程的每一步耗时：
        - 数据预处理时间
        - 编码时间
        - 模型推理时间
        - 后处理时间
        - 总时间
        """
```

**WebUI 中的体现方式**：
- 推理时间 breakdown 柱状图
- 每次预测的耗时趋势
- 设备 (CPU/GPU) 性能对比
- 吞吐量 (samples/sec)

---

#### 3.7 预测后处理优化
**模型能力**：数据标准化完成，可扩展

**当前状态**：仅简单反归一化

**建议实现**：
```python
# 后处理增强
class PostProcessor:
    def smooth_predictions(self, predictions, method='exponential'):
        """平滑预测结果"""

    def clip_outliers(self, predictions, std_threshold=3):
        """裁剪异常值"""

    def enforce_constraints(self, predictions):
        """应用约束：
        - high >= max(open, close)
        - low <= min(open, close)
        - volume > 0
        """
```

**WebUI 中的体现方式**：
- 后处理方法选择
- 平滑强度调整
- 约束条件选择

---

#### 3.8 混合精度推理（模型需扩展）
**模型能力**：暂未实现

**建议新增**：
```python
def predict_fp16(self, ...):
    """FP16 混合精度推理"""

def predict_int8(self, ...):
    """INT8 量化推理"""

def predict_onnx(self, ...):
    """ONNX 推理"""
```

**WebUI 中的体现方式**：
- 推理精度选择 (FP32/FP16/INT8)
- 推理框架选择 (PyTorch/ONNX)
- 速度vs精度权衡显示

---

### 🟢 优先级低 - 可选增强

#### 3.9 采样历史和重放
- 保存采样参数和结果
- 快速重放相同配置的预测

#### 3.10 模型内部状态检查
- 注意力权重可视化
- 隐藏层激活分布
- 梯度流分析

---

## 4. 功能实现优先级矩阵

```
┌────────────────┬──────────┬──────────┬──────────┐
│ 功能          │ 实现难度 │ 用户价值 │ 优先级   │
├────────────────┼──────────┼──────────┼──────────┤
│ 批量预测优化  │ ⭐⭐    │ 🎯 高   │ 🔴 1    │
│ Top-K 暴露   │ ⭐      │ 🎯 中   │ 🔴 2    │
│ 采样多样性分析 │ ⭐⭐    │ 🎯 中   │ 🔴 3    │
│ 不确定度估计  │ ⭐⭐⭐  │ 🎯 高   │ 🟡 4    │
│ 量化可视化    │ ⭐⭐    │ 🎯 低   │ 🟡 5    │
│ 性能监控      │ ⭐⭐    │ 🎯 中   │ 🟡 6    │
│ 后处理增强    │ ⭐⭐    │ 🎯 中   │ 🟡 7    │
│ 混合精度推理  │ ⭐⭐⭐⭐ │ 🎯 中   │ 🟢 8    │
└────────────────┴──────────┴──────────┴──────────┘

建议实现序列：
第 1 周：优先级 1-3（3 个功能）
  ├─ 批量预测启用
  ├─ Top-K 参数暴露
  └─ 采样一致性展示

第 2 周：优先级 4-6（3 个功能）
  ├─ 不确定度区间
  ├─ 量化过程可视化
  └─ 性能 Profiler

第 3 周：优先级 7-8（2 个功能）
  ├─ 后处理选项
  └─ 混合精度选择
```

---

## 5. 立即可实现的改进方案

### 5.1 最小可行产品 (MVP) - 1 周内完成

#### 功能 1：启用批量预测
```python
# app.py 中添加
@app.route('/api/predict-batch', methods=['POST'])
def batch_predict():
    """批量预测端点"""
    data = request.get_json()
    files = data.get('files')  # 多个文件路径

    results = {}
    for file_path in files:
        df, _ = load_data_file(file_path)
        pred = predictor.predict(
            df=df.iloc[:400],
            x_timestamp=df.iloc[:400]['timestamps'],
            y_timestamp=df.iloc[400:520]['timestamps'],
            pred_len=120,
            T=data.get('temperature', 1.0),
            top_p=data.get('top_p', 0.9),
            sample_count=data.get('sample_count', 1)
        )
        results[file_path] = pred.to_dict()

    return jsonify({'success': True, 'results': results})
```

#### 功能 2：暴露 Top-K 参数
```html
<!-- index.html 中添加 -->
<div class="form-group">
    <label for="top-k">Top-K 采样参数:</label>
    <input type="range" id="top-k" value="0" min="0" max="50" step="1">
    <span id="top-k-value">0</span> (0 = 禁用)
    <small class="form-text">0 表示禁用 Top-K，与 Top-P 组合使用</small>
</div>
```

```python
# app.py 中使用
top_k = int(data.get('top_k', 0))
pred_df = predictor.predict(
    ...,
    top_k=top_k if top_k > 0 else None,
    ...
)
```

#### 功能 3：采样一致性指标
```python
# 在预测后添加
if sample_count > 1:
    # 计算多采样的一致性
    predictions_variance = np.std(pred_df['close'])
    consistency = 1.0 / (1.0 + predictions_variance)  # 0-1, 越高越一致

    return jsonify({
        ...,
        'sampling_info': {
            'sample_count': sample_count,
            'consistency': float(consistency),
            'diversity': float(predictions_variance),
            'stable': consistency > 0.7
        }
    })
```

### 5.2 前端展示（HTML + JavaScript）

```javascript
// index.html 中新增
function displaySamplingInfo(result) {
    if (result.sampling_info) {
        const info = result.sampling_info;
        const stability = info.stable ? '✅ 稳定' : '⚠️ 不稳定';

        const html = `
            <div class="sampling-info">
                <h4>采样质量评估</h4>
                <p>采样数: ${info.sample_count}</p>
                <p>一致性: ${(info.consistency * 100).toFixed(1)}% ${stability}</p>
                <p>多样性: ${info.diversity.toFixed(4)}</p>
            </div>
        `;

        document.getElementById('comparison-section').insertAdjacentHTML('beforeend', html);
    }
}
```

---

## 6. 总结

### 模型中已有但 WebUI 未展现的功能：

| 功能 | 模型支持 | WebUI 展现 | 建议 |
|------|---------|---------|------|
| 批量预测 | ✅ | ❌ | 立即启用 |
| Top-K 采样 | ✅ | ❌ | 立即暴露 |
| 采样多样性 | ✅ | ❌ | 立即展示 |
| 量化编码 | ✅ | ❌ | 近期可视化 |
| 性能监控 | ⚠️ 部分 | ❌ | 近期实现 |

### 模型中缺失的功能：

| 功能 | 模型支持 | 建议 | 优先级 |
|------|---------|------|--------|
| 不确定度估计 | ❌ | 需要扩展 | 🔴 高 |
| 采样策略对比 | ⚠️ 部分 | 完整支持 | 🔴 高 |
| 混合精度推理 | ❌ | 可选实现 | 🟢 低 |
| 异常检测 | ❌ | 可选实现 | 🟢 低 |

### 立即行动建议：

**第 1 周**（高影响，低成本）：
- ✅ 启用 `predict_batch()`
- ✅ 暴露 Top-K 参数
- ✅ 显示采样一致性指标

**第 2-3 周**（中等难度，高价值）：
- ✅ 量化过程可视化
- ✅ 性能监控面板
- ✅ 不确定度区间

**第 4+ 周**（高难度，可选）：
- ✅ 混合精度推理
- ✅ 采样策略完整对比
- ✅ 异常检测

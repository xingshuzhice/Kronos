# WebUI 功能分析与增强建议

## 执行摘要

通过对 Kronos WebUI 的全面分析，已识别出 **12 个优先级别的功能增强建议**，涵盖数据管理、预测功能、分析工具、用户体验等多个维度。

---

## 当前功能清单

### ✅ 已实现的核心功能

| 功能 | 状态 | 实现位置 |
|------|------|---------|
| 模型加载 | ✅ | `app.py` 行 626-663 |
| 数据加载 (CSV/Feather) | ✅ | `app.py` 行 341-402 |
| 时间窗口滑块 | ✅ | `index.html` 行 510-532 |
| K 线图可视化 | ✅ | `app.py` 行 209-328 |
| 预测执行 | ✅ | `app.py` 行 404-624 |
| 误差对比分析 | ✅ | `index.html` 行 583-631 |
| 结果保存 (JSON) | ✅ | `app.py` 行 125-207 |
| 温度/采样参数控制 | ✅ | `index.html` 行 547-566 |
| 多模型支持 | ✅ | `app.py` 行 33-58 |
| 多设备支持 (CPU/GPU/MPS) | ✅ | `index.html` 行 462-469 |

### ❌ 缺失或不完整的功能

| 功能 | 优先级 | 复杂度 | 影响度 |
|------|--------|--------|--------|
| **1. 批量预测** | 🔴 高 | ⭐⭐⭐ | 🎯 高 |
| **2. 预测历史管理** | 🔴 高 | ⭐⭐ | 🎯 高 |
| **3. 模型对比分析** | 🔴 高 | ⭐⭐⭐ | 🎯 高 |
| **4. 高级可视化** | 🟡 中 | ⭐⭐⭐⭐ | 🎯 中 |
| **5. 性能监控面板** | 🟡 中 | ⭐⭐⭐ | 🎯 中 |
| **6. 数据预处理工具** | 🟡 中 | ⭐⭐ | 🎯 中 |
| **7. 参数自动优化** | 🟡 中 | ⭐⭐⭐⭐ | 🎯 低 |
| **8. 结果导出功能** | 🟢 低 | ⭐⭐ | 🎯 中 |
| **9. 实时通知系统** | 🟢 低 | ⭐⭐⭐ | 🎯 低 |
| **10. API 文档** | 🟢 低 | ⭐ | 🎯 高 |
| **11. 数据集管理器** | 🟡 中 | ⭐⭐⭐ | 🎯 中 |
| **12. 回测框架** | 🔴 高 | ⭐⭐⭐⭐⭐ | 🎯 高 |

---

## 详细功能需求说明

### 🔴 优先级高 - 立即建议实现

#### 1. 批量预测（Batch Prediction）

**当前状态**：仅支持单个文件单次预测

**需求描述**：
- 支持一次选择多个数据文件
- 支持预设多个预测参数组合
- 后台并行处理预测任务
- 支持预测队列管理

**实现位置建议**：
```
webui/
├── app.py
│   ├── 新增: @app.route('/api/batch-predict', methods=['POST'])
│   ├── 新增: def batch_predict_worker(queue, results)
│   └── 新增: def get_batch_status()
├── static/
│   ├── 新增: batch_predictions.js
│   └── 新增: queue_manager.js
└── templates/
    └── 新增: batch_prediction.html
```

**核心代码示例**：
```python
@app.route('/api/batch-predict', methods=['POST'])
def batch_predict():
    """批量预测端点"""
    data = request.get_json()
    files = data.get('files')  # 文件列表
    params_list = data.get('params_list')  # 参数列表

    # 创建任务队列
    task_id = create_batch_task(files, params_list)

    # 后台处理
    thread = Thread(target=process_batch_predictions, args=(task_id,))
    thread.start()

    return jsonify({'task_id': task_id})

@app.route('/api/batch-status/<task_id>', methods=['GET'])
def get_batch_status(task_id):
    """获取批量预测进度"""
    return jsonify({
        'task_id': task_id,
        'total': batch_tasks[task_id]['total'],
        'completed': batch_tasks[task_id]['completed'],
        'results': batch_tasks[task_id]['results'],
        'status': batch_tasks[task_id]['status']
    })
```

**前端集成**：
- 多文件选择器
- 参数组合编辑器
- 进度条和队列显示
- 结果汇总表格

**预期收益**：
- ✅ 大幅提升用户工作效率
- ✅ 支持大规模数据处理
- ✅ 启用批量对比分析

---

#### 2. 预测历史管理（Prediction History）

**当前状态**：预测结果保存为 JSON 文件，无集中管理

**需求描述**：
- 数据库存储所有预测记录（SQLite）
- 预测历史浏览和查询界面
- 快速对比不同时间的预测
- 预测版本控制

**实现位置建议**：
```
webui/
├── database.py (新增)
│   ├── class PredictionHistory
│   ├── def save_prediction(...)
│   └── def query_history(...)
├── app.py
│   ├── 新增: @app.route('/api/history', methods=['GET'])
│   ├── 新增: @app.route('/api/history/<id>', methods=['GET'])
│   └── 新增: @app.route('/api/history/delete/<id>', methods=['DELETE'])
└── templates/
    └── 新增: history_manager.html
```

**数据库架构**：
```python
class PredictionRecord(Base):
    __tablename__ = 'predictions'

    id = Column(String, primary_key=True)  # UUID
    timestamp = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String)
    device = Column(String)
    data_file = Column(String)
    lookback = Column(Integer)
    pred_len = Column(Integer)
    temperature = Column(Float)
    top_p = Column(Float)
    sample_count = Column(Integer)
    mae = Column(Float)
    rmse = Column(Float)
    mape = Column(Float)
    prediction_results = Column(JSON)  # 序列化
    tags = Column(String)  # 用户标签
    notes = Column(String)  # 用户备注
```

**前端集成**：
- 时间线视图
- 高级搜索和过滤
- 批量操作（删除、导出、比较）
- 标签和备注系统

**预期收益**：
- ✅ 完整的审计追踪
- ✅ 实验版本管理
- ✅ 知识库积累

---

#### 3. 模型对比分析（Model Comparison）

**当前状态**：一次只能加载一个模型

**需求描述**：
- 同时加载多个模型进行对比
- 相同数据下模型输出对比
- 性能指标对比表格
- 模型排名和推荐

**实现位置建议**：
```
webui/
├── app.py
│   ├── 新增: @app.route('/api/compare-models', methods=['POST'])
│   ├── 新增: def load_multiple_models(model_keys)
│   └── 新增: def compare_predictions(...)
├── templates/
│   └── 新增: model_comparison.html
└── static/
    └── 新增: comparison_utils.js
```

**核心代码示例**：
```python
@app.route('/api/compare-models', methods=['POST'])
def compare_models():
    """对比多个模型"""
    data = request.get_json()
    model_keys = data.get('model_keys', [])
    file_path = data.get('file_path')
    lookback = data.get('lookback', 400)
    pred_len = data.get('pred_len', 120)

    # 加载多个模型
    models = {}
    predictors = {}
    for key in model_keys:
        config = AVAILABLE_MODELS[key]
        tok = KronosTokenizer.from_pretrained(config['tokenizer_id'])
        mod = Kronos.from_pretrained(config['model_id'])
        pred = KronosPredictor(mod, tok, max_context=config['context_length'])

        models[key] = mod
        predictors[key] = pred

    # 对同一数据进行预测
    df, _ = load_data_file(file_path)
    x_df = df.iloc[:lookback]
    x_timestamp = df.iloc[:lookback]['timestamps']
    y_timestamp = df.iloc[lookback:lookback+pred_len]['timestamps']

    results = {}
    metrics = {}

    for key, predictor in predictors.items():
        pred_df = predictor.predict(x_df, x_timestamp, y_timestamp, pred_len)
        results[key] = pred_df.to_dict()

        # 如果有实际数据进行对比
        if len(df) >= lookback + pred_len:
            actual_df = df.iloc[lookback:lookback+pred_len]
            mae, rmse, mape = calculate_metrics(pred_df, actual_df)
            metrics[key] = {'mae': mae, 'rmse': rmse, 'mape': mape}

    # 排序模型（按 MAPE）
    ranked_models = sorted(metrics.items(), key=lambda x: x[1]['mape'])

    return jsonify({
        'results': results,
        'metrics': metrics,
        'ranked': [m[0] for m in ranked_models]
    })
```

**前端集成**：
- 模型复选框选择
- 并排 K 线图对比
- 性能指标对比表
- 统计信息和推荐

**预期收益**：
- ✅ 快速选择最优模型
- ✅ 量化模型性能差异
- ✅ 支持模型选择决策

---

#### 12. 回测框架（Backtesting Framework）

**当前状态**：仅展示预测结果，无策略评估

**需求描述**：
- 基于预测结果的回测引擎
- 支持多种交易策略
- 风险指标计算（Sharpe、Sortino、最大回撤）
- 对比基准收益

**实现位置建议**：
```
webui/
├── backtest/
│   ├── __init__.py
│   ├── engine.py (新增)
│   ├── strategies.py (新增)
│   └── metrics.py (新增)
├── app.py
│   └── 新增: @app.route('/api/backtest', methods=['POST'])
└── templates/
    └── 新增: backtest_analysis.html
```

**策略示例**：
```python
class SimpleStrategy:
    """基于阈值的简单策略"""
    def __init__(self, threshold=0.01):
        self.threshold = threshold

    def generate_signals(self, predictions, actual):
        signals = []
        for pred, act in zip(predictions, actual):
            # 预测上升 > 阈值 → 买入
            if pred['close'] > act['close'] * (1 + self.threshold):
                signals.append(1)  # BUY
            # 预测下降 > 阈值 → 卖出
            elif pred['close'] < act['close'] * (1 - self.threshold):
                signals.append(-1)  # SELL
            else:
                signals.append(0)  # HOLD
        return signals

class RollingStrategy:
    """滚动预测策略"""
    def __init__(self, lookback=400, pred_len=120):
        self.lookback = lookback
        self.pred_len = pred_len

    def run(self, df, predictor, threshold=0.01):
        """运行回测"""
        portfolio_values = [100]  # 初始资金 100
        positions = 0

        for i in range(self.lookback, len(df) - self.pred_len):
            # 生成预测
            x_df = df.iloc[i-self.lookback:i]
            pred_df = predictor.predict(x_df, ...)

            # 生成信号
            signal = self._generate_signal(pred_df, df.iloc[i])

            # 执行交易
            if signal == 1 and positions == 0:
                positions = 1
            elif signal == -1 and positions == 1:
                positions = 0

            # 更新投资组合价值
            current_price = df.iloc[i]['close']
            portfolio_values.append(portfolio_values[-1] * (1 + positions * (df.iloc[i+1]['close'] - current_price) / current_price))

        return portfolio_values
```

**性能指标**：
```python
def calculate_metrics(returns):
    """计算回测指标"""
    metrics = {
        'total_return': (returns[-1] - returns[0]) / returns[0],
        'annual_return': total_return ** (252 / len(returns)) - 1,
        'sharpe_ratio': np.mean(returns) / np.std(returns) * np.sqrt(252),
        'max_drawdown': calculate_max_drawdown(returns),
        'win_rate': calculate_win_rate(returns)
    }
    return metrics
```

**前端集成**：
- 策略参数编辑器
- 回测结果曲线图
- 性能指标面板
- 对比基准

**预期收益**：
- ✅ 量化预测可用性
- ✅ 支持策略验证
- ✅ 风险评估工具

---

### 🟡 优先级中 - 建议后续实现

#### 4. 高级可视化（Advanced Visualization）

**增强建议**：
1. **多视图支持**：
   - 蜡烛图（已有）
   - 曲线图（增强对比）
   - 柱状图（成交量）
   - 热力图（相关性）

2. **交互增强**：
   - 鼠标悬停显示详细信息
   - 区间放大/缩小
   - 指标叠加（移动平均、布林线）
   - 实时注释

3. **对比分析**：
   - 多时间段对比
   - 多模型输出并排显示
   - 预测置信度区间

**实现建议**：
```javascript
// 使用 Plotly 的高级特性
function createAdvancedChart(data) {
    const fig = go.Figure();

    // K 线
    fig.add_trace(go.Candlestick({...}));

    // 成交量柱状
    fig.add_trace(go.Bar({
        x: data.timestamps,
        y: data.volume,
        yaxis: 'y2',
        name: '成交量'
    }));

    // 移动平均线
    fig.add_trace(go.Scatter({
        x: data.timestamps,
        y: calculateMA(data.close, 20),
        name: 'MA20'
    }));

    // 双 Y 轴配置
    fig.update_layout({
        yaxis2: {
            title: '成交量',
            overlaying: 'y',
            side: 'right'
        }
    });

    return fig;
}
```

---

#### 5. 性能监控面板（Performance Dashboard）

**需求**：
- 实时资源使用情况（CPU、内存、GPU）
- 预测延迟统计
- 吞吐量监控
- 模型推理时间分布

**实现建议**：
```python
# 性能监控中间件
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'predictions': [],
            'latencies': [],
            'errors': []
        }

    def track_prediction(self, model_key, latency, success):
        self.metrics['predictions'].append({
            'model': model_key,
            'timestamp': datetime.utcnow(),
            'latency': latency,
            'success': success
        })
```

---

#### 6. 数据预处理工具（Data Preprocessing Tools）

**需求**：
- 缺失值填充
- 异常值检测和处理
- 数据标准化选项
- 特征工程助手

**实现建议**：
```python
@app.route('/api/preprocess', methods=['POST'])
def preprocess_data():
    """数据预处理"""
    data = request.get_json()
    file_path = data.get('file_path')
    options = data.get('options')  # 预处理选项

    df, _ = load_data_file(file_path)

    if options.get('fill_missing'):
        df = df.fillna(method='ffill')

    if options.get('remove_outliers'):
        df = remove_outliers(df, std_devs=3)

    if options.get('normalize'):
        for col in ['open', 'high', 'low', 'close']:
            df[col] = (df[col] - df[col].mean()) / df[col].std()

    return jsonify({'preview': df.head().to_dict()})
```

---

#### 11. 数据集管理器（Dataset Manager）

**需求**：
- 数据集标签和分类
- 数据统计摘要
- 数据质量检查
- 版本控制

**实现建议**：
```python
class DatasetManager:
    def __init__(self):
        self.datasets = {}

    def register_dataset(self, name, path, metadata):
        """注册数据集"""
        self.datasets[name] = {
            'path': path,
            'metadata': metadata,
            'registered_at': datetime.utcnow(),
            'access_count': 0
        }

    def get_dataset_stats(self, name):
        """获取数据集统计"""
        df, _ = load_data_file(self.datasets[name]['path'])
        return {
            'rows': len(df),
            'columns': len(df.columns),
            'missing_values': df.isnull().sum().to_dict(),
            'price_range': {...}
        }
```

---

### 🟢 优先级低 - 可选增强

#### 8. 结果导出功能（Export Results）

**需求**：
- 导出为 CSV、Excel、PDF
- 包含图表的报告生成
- 批量导出

**实现建议**：
```python
@app.route('/api/export/<export_format>', methods=['POST'])
def export_results(export_format):
    """导出预测结果"""
    data = request.get_json()
    results = data.get('results')

    if export_format == 'csv':
        df = pd.DataFrame(results)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        return Response(csv_buffer.getvalue(), mimetype='text/csv')

    elif export_format == 'excel':
        df = pd.DataFrame(results)
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False)
        return Response(excel_buffer.getvalue(), mimetype='application/vnd.ms-excel')

    elif export_format == 'pdf':
        # 生成带图表的 PDF 报告
        report = generate_pdf_report(results)
        return Response(report, mimetype='application/pdf')
```

---

#### 9. 实时通知系统（Notification System）

**需求**：
- 预测完成通知
- 错误告警
- 批量任务进度推送

**实现建议**：
```python
# 使用 WebSocket 实现实时通知
from flask_socketio import SocketIO, emit

socketio = SocketIO(app)

@socketio.on('connect')
def handle_connect():
    emit('response', {'data': '连接成功'})

def notify_prediction_complete(task_id, result):
    """预测完成通知"""
    socketio.emit('prediction_complete', {
        'task_id': task_id,
        'result': result
    }, broadcast=True)
```

---

#### 10. API 文档（API Documentation）

**需求**：
- Swagger/OpenAPI 集成
- 交互式 API 测试
- SDK 生成

**实现建议**：
```python
from flasgger import Swagger

swagger = Swagger(app)

@app.route('/api/predict', methods=['POST'])
def predict():
    """
    执行预测
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            file_path:
              type: string
              description: 数据文件路径
            lookback:
              type: integer
              description: 回溯窗口大小
    responses:
      200:
        description: 预测成功
    """
    # 实现...
```

---

## 实现优先级矩阵

```
优先级对标:
┌──────────────────┬─────────────┬─────────────┐
│ 优先级 │ 影响度 │ 复杂度 │ 建议 │
├──────────────────┼─────────────┼─────────────┤
│ 🔴 高 │ 🎯 高 │ ⭐⭐⭐ │ 第 1-2 迭代 │
│ 🟡 中 │ 🎯 中 │ ⭐⭐⭐⭐ │ 第 3-4 迭代 │
│ 🟢 低 │ 🎯 低 │ ⭐⭐ │ 第 5+ 迭代 │
└──────────────────┴─────────────┴─────────────┘

建议实现序列:
1️⃣  (高优先级 & 相对简单)
    ↓ 批量预测
    ↓ 预测历史管理
    ↓ 结果导出

2️⃣  (高影响度)
    ↓ 模型对比
    ↓ 高级可视化
    ↓ 性能监控

3️⃣  (增强功能)
    ↓ 数据预处理工具
    ↓ 数据集管理器
    ↓ 回测框架

4️⃣  (可选/未来)
    ↓ 参数自动优化
    ↓ 实时通知
    ↓ API 文档
```

---

## 技术选型建议

### 后端增强

| 技术 | 用途 | 优势 |
|------|------|------|
| **SQLAlchemy** | ORM 数据库 | 轻量、易于扩展 |
| **Celery** | 异步任务队列 | 支持分布式处理 |
| **Redis** | 缓存/队列 | 高性能、内存存储 |
| **APScheduler** | 定时任务 | 本地调度方案 |
| **Prometheus** | 性能监控 | 标准开源方案 |

### 前端增强

| 技术 | 用途 | 优势 |
|------|------|------|
| **Vue.js/React** | 前端框架 | 组件化开发 |
| **ECharts** | 高级可视化 | 功能丰富 |
| **WebSocket** | 实时通信 | 低延迟 |
| **Tailwind CSS** | 样式框架 | 快速开发 |

---

## 迭代计划示例

### 第 1 阶段（2-3 周）- 基础增强
- ✅ 批量预测功能
- ✅ 基础历史管理
- ✅ CSV 导出

### 第 2 阶段（3-4 周）- 高级功能
- ✅ 模型对比分析
- ✅ 高级可视化
- ✅ 性能监控

### 第 3 阶段（4-5 周）- 完整框架
- ✅ 数据预处理工具
- ✅ 回测引擎
- ✅ 数据集管理器

### 第 4 阶段（持续）- 优化和扩展
- ✅ 参数优化
- ✅ 通知系统
- ✅ API 文档和 SDK

---

## 总结

通过系统的功能分析，已识别出当前 WebUI 的主要改进方向。建议优先实现**批量预测**、**预测历史**和**模型对比**三个核心功能，这些功能具有：

1. **高业务价值**：大幅提升用户工作效率
2. **相对可控复杂度**：使用现有架构可实现
3. **快速交付**：2-3 周内可完成
4. **验证市场**：直接收集用户反馈

后续可逐步增加高级分析和自动化功能，最终形成完整的金融预测分析平台。

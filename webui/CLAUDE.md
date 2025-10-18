# WebUI 模块代码逻辑详解

## 概述

`webui` 模块提供了一个交互式的网页界面，使用户能够直观地使用 Kronos 模型进行金融预测。采用 Flask 后端和现代前端框架，支持实时预测、参数调整和结果可视化。

### 核心特性
- ✅ 直观的网页用户界面
- ✅ 支持多种模型和计算设备
- ✅ 灵活的时间窗口滑块选择
- ✅ 实时预测和 K 线图展示
- ✅ 预测结果与实际数据对比分析
- ✅ CSV/Feather 数据格式支持
- ✅ 预测结果自动保存

---

## 文件结构与职责

```
webui/
├── app.py                     # Flask 后端应用
├── run.py                     # Web UI 启动脚本
├── start.sh                   # Shell 启动脚本
├── requirements.txt           # 依赖项
├── templates/
│   └── index.html            # 前端界面（HTML + CSS + JS）
├── prediction_results/       # 预测结果保存目录
└── README.md                 # 使用说明

```

---

## 1. 后端架构 - app.py

### 1.1 Flask 应用配置

```python
# 全局配置
app = Flask(__name__)
CORS(app)  # 启用跨域请求

# 全局变量存储模型
tokenizer = None
model = None
predictor = None
```

### 1.2 模型配置

```python
AVAILABLE_MODELS = {
    'kronos-mini': {
        'name': 'Kronos-mini',
        'model_id': 'NeoQuasar/Kronos-mini',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
        'context_length': 2048,
        'params': '4.1M',
        'description': '轻量级模型，适合快速预测'
    },
    'kronos-small': {...},
    'kronos-base': {...}
}
```

**模型对比**：

| 模型 | 参数数量 | 上下文长度 | 用途 |
|------|---------|----------|------|
| **mini** | 4.1M | 2048 | 快速演示、资源受限 |
| **small** | 24.7M | 512 | 生产环境（推荐） |
| **base** | 102.3M | 512 | 高精度预测 |

### 1.3 核心 API 端点

#### 1.3.1 数据加载

**端点**：`POST /api/load-data`

```python
def load_data():
    """加载数据文件并进行预处理"""

    # 1. 文件验证
    file_path = request.json.get('file_path')

    # 2. 加载文件（CSV 或 Feather）
    if file_path.endswith('.csv'):
        df = pd.read_csv(file_path)
    elif file_path.endswith('.feather'):
        df = pd.read_feather(file_path)

    # 3. 列名检查
    required_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_cols):
        return error_response("缺少必需列")

    # 4. 时间戳处理
    if 'timestamps' in df.columns:
        df['timestamps'] = pd.to_datetime(df['timestamps'])
    elif 'timestamp' in df.columns:
        df['timestamps'] = pd.to_datetime(df['timestamp'])
    elif 'date' in df.columns:
        df['timestamps'] = pd.to_datetime(df['date'])
    else:
        # 自动生成时间戳
        df['timestamps'] = pd.date_range(start='2024-01-01', periods=len(df), freq='1H')

    # 5. 数据类型转换
    for col in ['open', 'high', 'low', 'close']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 6. 清理 NaN 值
    df = df.dropna()

    # 7. 检测时间频率
    timeframe = detect_timeframe(df)

    return success_response(data_info)
```

**返回数据**：
```json
{
    "rows": 10000,
    "columns": ["open", "high", "low", "close", "volume"],
    "start_date": "2024-01-01T00:00:00",
    "end_date": "2024-12-31T23:00:00",
    "price_range": {"min": 100.5, "max": 105.3},
    "timeframe": "1 hours",
    "prediction_columns": ["open", "high", "low", "close", "volume"]
}
```

#### 1.3.2 模型加载

**端点**：`POST /api/load-model`

```python
def load_model():
    """加载指定的 Kronos 模型"""

    global tokenizer, model, predictor

    model_key = request.json.get('model_key', 'kronos-small')
    device = request.json.get('device', 'cpu')

    model_config = AVAILABLE_MODELS[model_key]

    # 1. 从 Hugging Face Hub 加载
    tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
    model = Kronos.from_pretrained(model_config['model_id'])

    # 2. 创建预测器
    predictor = KronosPredictor(
        model,
        tokenizer,
        device=device,
        max_context=model_config['context_length']
    )

    return success_response({
        'name': model_config['name'],
        'params': model_config['params'],
        'context_length': model_config['context_length'],
        'device': device
    })
```

#### 1.3.3 预测执行

**端点**：`POST /api/predict`

```python
def predict():
    """执行 Kronos 模型预测"""

    # 1. 参数解析
    file_path = request.json.get('file_path')
    lookback = int(request.json.get('lookback', 400))  # 固定 400
    pred_len = int(request.json.get('pred_len', 120))  # 固定 120
    temperature = float(request.json.get('temperature', 1.0))
    top_p = float(request.json.get('top_p', 0.9))
    sample_count = int(request.json.get('sample_count', 1))
    start_date = request.json.get('start_date')  # 可选的时间范围

    # 2. 数据加载
    df, error = load_data_file(file_path)
    if error:
        return error_response(error)

    # 3. 时间范围选择
    if start_date:
        # 自定义时间范围
        start_dt = pd.to_datetime(start_date)
        mask = df['timestamps'] >= start_dt
        time_range_df = df[mask]
        x_df = time_range_df.iloc[:lookback][required_cols]
        x_timestamp = time_range_df.iloc[:lookback]['timestamps']
        y_timestamp = time_range_df.iloc[lookback:lookback+pred_len]['timestamps']
    else:
        # 最新数据
        x_df = df.iloc[:lookback][required_cols]
        x_timestamp = df.iloc[:lookback]['timestamps']
        y_timestamp = df.iloc[lookback:lookback+pred_len]['timestamps']

    # 4. 执行预测
    pred_df = predictor.predict(
        df=x_df,
        x_timestamp=x_timestamp,
        y_timestamp=y_timestamp,
        pred_len=pred_len,
        T=temperature,
        top_p=top_p,
        sample_count=sample_count
    )

    # 5. 生成对比数据（如果可用）
    if len(df) >= lookback + pred_len:
        actual_df = df.iloc[lookback:lookback+pred_len]

    # 6. 创建可视化图表
    chart_json = create_prediction_chart(df, pred_df, lookback, pred_len, actual_df)

    # 7. 保存结果
    save_prediction_results(...)

    return success_response({
        'chart': chart_json,
        'prediction_results': prediction_results,
        'actual_data': actual_data,
        'has_comparison': len(actual_data) > 0
    })
```

### 1.4 可视化 - K 线图表

```python
def create_prediction_chart(df, pred_df, lookback, pred_len, actual_df=None):
    """创建 Plotly K 线图表"""

    fig = go.Figure()

    # 1. 历史数据（蓝绿色）
    fig.add_trace(go.Candlestick(
        x=historical_df['timestamps'],
        open=historical_df['open'],
        high=historical_df['high'],
        low=historical_df['low'],
        close=historical_df['close'],
        name='历史数据（400个数据点）',
        increasing_line_color='#26A69A',
        decreasing_line_color='#EF5350'
    ))

    # 2. 预测数据（绿色）
    fig.add_trace(go.Candlestick(
        x=pred_timestamps,
        open=pred_df['open'],
        high=pred_df['high'],
        low=pred_df['low'],
        close=pred_df['close'],
        name='预测数据（120个数据点）',
        increasing_line_color='#66BB6A',
        decreasing_line_color='#FF7043'
    ))

    # 3. 实际数据（橙色，用于对比）
    if actual_df is not None:
        fig.add_trace(go.Candlestick(
            x=actual_timestamps,
            open=actual_df['open'],
            high=actual_df['high'],
            low=actual_df['low'],
            close=actual_df['close'],
            name='实际数据（120个数据点）',
            increasing_line_color='#FF9800',
            decreasing_line_color='#F44336'
        ))

    # 4. 图表配置
    fig.update_layout(
        title='Kronos 金融预测 - 400 历史 + 120 预测 vs 120 实际',
        xaxis_title='时间',
        yaxis_title='价格',
        height=600
    )

    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
```

### 1.5 结果保存

```python
def save_prediction_results(file_path, prediction_type, prediction_results, actual_data, ...):
    """自动保存预测结果为 JSON 文件"""

    save_data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'file_path': file_path,
        'prediction_type': prediction_type,
        'prediction_params': {
            'lookback': lookback,
            'pred_len': pred_len,
            'temperature': temperature,
            'top_p': top_p,
            'sample_count': sample_count
        },
        'input_data_summary': {
            'rows': len(input_data),
            'columns': list(input_data.columns),
            'price_range': {...},
            'last_values': {...}
        },
        'prediction_results': prediction_results,
        'actual_data': actual_data,
        'analysis': {
            'continuity': {
                'gaps': {...},
                'gap_percentages': {...}
            }
        }
    }

    # 保存为 JSON
    filename = f'prediction_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(os.path.join('prediction_results', filename), 'w') as f:
        json.dump(save_data, f, indent=2)
```

---

## 2. 前端架构 - index.html

### 2.1 页面结构

```html
<div class="main-content">
    <!-- 左侧：控制面板 -->
    <div class="control-panel">
        <!-- 模型选择 -->
        <!-- 数据文件选择 -->
        <!-- 时间窗口滑块 -->
        <!-- 预测参数 -->
        <!-- 预测按钮 -->
    </div>

    <!-- 右侧：图表容器 -->
    <div class="chart-container">
        <!-- K 线图 -->
        <!-- 对比分析 -->
    </div>
</div>
```

### 2.2 关键 JavaScript 函数

#### 2.2.1 应用初始化

```javascript
async function initializeApp() {
    console.log('🚀 初始化 Kronos Web UI...');

    // 1. 加载可用模型
    await loadAvailableModels();

    // 2. 加载数据文件列表
    await loadDataFiles();

    // 3. 设置事件监听
    setupEventListeners();

    // 4. 初始化时间滑块
    initializeTimeSlider();
}
```

#### 2.2.2 模型加载

```javascript
async function loadModel() {
    const modelKey = document.getElementById('model-select').value;
    const device = document.getElementById('device-select').value;

    try {
        showLoading(true);

        const response = await axios.post('/api/load-model', {
            model_key: modelKey,
            device: device
        });

        if (response.data.success) {
            modelLoaded = true;
            showStatus('success', response.data.message);
            document.getElementById('predict-btn').disabled = false;
        }
    } catch (error) {
        showStatus('error', `模型加载失败: ${error.message}`);
    } finally {
        showLoading(false);
    }
}
```

#### 2.2.3 时间窗口滑块

```javascript
// 时间窗口参数
const windowSize = 520;  // 固定：400 + 120
let sliderData = {
    startDate: null,
    endDate: null,
    totalRows: 0
};

function updateStartHandle(percentage) {
    const windowPercentage = windowSize / sliderData.totalRows;

    // 确保窗口不超出范围
    if (percentage + windowPercentage > 1) {
        percentage = 1 - windowPercentage;
    }

    // 更新起始和结束位置
    startHandle.style.left = (percentage * 100) + '%';
    endHandle.style.left = ((percentage + windowPercentage) * 100) + '%';
}

function updateEndHandle(percentage) {
    const windowPercentage = windowSize / sliderData.totalRows;

    // 确保窗口不低于 0
    if (percentage - windowPercentage < 0) {
        percentage = windowPercentage;
    }

    // 更新起始和结束位置
    endHandle.style.left = (percentage * 100) + '%';
    startHandle.style.left = ((percentage - windowPercentage) * 100) + '%';
}
```

#### 2.2.4 预测执行

```javascript
async function startPrediction() {
    // 1. 验证
    if (!currentDataFile) {
        showStatus('error', '请先加载数据文件');
        return;
    }

    if (!modelLoaded) {
        showStatus('error', '请先加载模型');
        return;
    }

    try {
        showLoading(true);

        // 2. 收集参数
        const lookback = 400;  // 固定
        const predLen = 120;   // 固定

        // 获取滑块选择的开始日期
        const startPercentage = parseFloat(
            document.getElementById('start-handle').style.left
        ) / 100;
        const startDate = calculateDateFromPercentage(startPercentage);

        // 获取预测质量参数
        const temperature = parseFloat(document.getElementById('temperature').value);
        const topP = parseFloat(document.getElementById('top-p').value);
        const sampleCount = parseInt(document.getElementById('sample-count').value);

        // 3. 发送预测请求
        const response = await axios.post('/api/predict', {
            file_path: currentDataFile,
            lookback: lookback,
            pred_len: predLen,
            start_date: startDate.toISOString().slice(0, 16),
            temperature: temperature,
            top_p: topP,
            sample_count: sampleCount
        });

        // 4. 显示结果
        if (response.data.success) {
            displayPredictionResult(response.data);
            showStatus('success', response.data.message);
        }
    } catch (error) {
        showStatus('error', `预测失败: ${error.message}`);
    } finally {
        showLoading(false);
    }
}
```

#### 2.2.5 结果对比分析

```javascript
function displayComparisonAnalysis(result) {
    // 计算误差指标
    const errorStats = getPredictionQuality(
        result.prediction_results,
        result.actual_data
    );

    // 显示 MAE、RMSE、MAPE
    document.getElementById('mae').textContent = errorStats.mae.toFixed(4);
    document.getElementById('rmse').textContent = errorStats.rmse.toFixed(4);
    document.getElementById('mape').textContent = errorStats.mape.toFixed(2);

    // 填充对比表格
    fillComparisonTable(result.prediction_results, result.actual_data);
}

function getPredictionQuality(predictions, actuals) {
    const minLen = Math.min(predictions.length, actuals.length);
    let mae = 0, rmse = 0, mape = 0;

    for (let i = 0; i < minLen; i++) {
        const pred = predictions[i];
        const act = actuals[i];

        // 使用收盘价计算误差
        const error = Math.abs(pred.close - act.close);
        const percentError = (error / act.close) * 100;

        mae += error;
        rmse += error * error;
        mape += percentError;
    }

    return {
        mae: mae / minLen,
        rmse: Math.sqrt(rmse / minLen),
        mape: mape / minLen
    };
}
```

### 2.3 预测参数控制

| 参数 | 范围 | 作用 | 推荐值 |
|------|------|------|--------|
| **Temperature (T)** | 0.1 - 2.0 | 控制预测随机性 | 1.0 - 1.2 |
| **Nucleus Sampling (top_p)** | 0.1 - 1.0 | 控制多样性 | 0.9 - 1.0 |
| **Sample Count** | 1 - 5 | 生成多个样本并平均 | 1 - 3 |

---

## 3. 启动和使用

### 3.1 启动方式

**方式 1：Python 脚本**
```bash
cd webui
python run.py
```

**方式 2：Shell 脚本**
```bash
cd webui
chmod +x start.sh
./start.sh
```

**方式 3：直接运行 Flask**
```bash
cd webui
python app.py
```

### 3.2 依赖安装

```bash
pip install -r requirements.txt
```

**依赖项**：
```
flask==2.3.3
flask-cors==4.0.0
pandas==2.2.2
numpy==1.24.3
plotly==5.17.0
torch>=2.1.0
huggingface_hub==0.33.1
```

### 3.3 使用流程

```
1. 启动应用
   ↓
2. 浏览器访问 http://localhost:7070
   ↓
3. 加载 Kronos 模型
   └─ 选择模型 (mini/small/base)
   └─ 选择设备 (CPU/CUDA/MPS)
   └─ 点击"加载模型"
   ↓
4. 加载数据文件
   └─ 选择 CSV/Feather 文件
   └─ 点击"加载数据"
   ↓
5. 调整时间窗口
   └─ 使用滑块选择 400+120 窗口
   ↓
6. 调整预测参数
   └─ 温度 (T)
   └─ 核采样 (top_p)
   └─ 样本数量
   ↓
7. 执行预测
   └─ 点击"开始预测"
   ↓
8. 查看结果
   └─ K 线图表
   └─ 预测 vs 实际对比
   └─ 误差指标（MAE/RMSE/MAPE）
   ↓
9. 结果自动保存
   └─ prediction_results/ 目录
```

---

## 4. 常见问题与故障排查

### 问题 1：端口 7070 已被占用

**错误信息**：
```
Address already in use: port 7070
```

**解决方案**：
```python
# 在 app.py 或 run.py 中修改端口
app.run(port=8080)  # 改为其他端口
```

### 问题 2：模型加载失败

**错误信息**：
```
Connection timeout: Failed to download model
```

**解决方案**：
- 检查网络连接
- 使用代理：设置 `HF_ENDPOINT` 环境变量
- 本地加载：使用本地模型路径

### 问题 3：数据格式错误

**错误信息**：
```
Missing required columns: ['open', 'high', 'low', 'close']
```

**解决方案**：
- 确保 CSV 文件包含必需列
- 检查列名大小写是否正确
- 数据类型需为数字类型

### 问题 4：时间窗口滑块不响应

**原因**：
- 数据长度不足 520 个数据点
- JavaScript 初始化失败

**解决方案**：
- 确保加载的数据至少有 520 行
- 查看浏览器控制台是否有错误

### 问题 5：CUDA/GPU 不可用

**错误信息**：
```
CUDA out of memory
```

**解决方案**：
- 切换设备为 CPU
- 使用轻量级模型 (mini)
- 减少 sample_count

---

## 5. 数据流转图

```
用户界面 (HTML + JS)
    ↓
API 请求 (Axios)
    ├─ /api/load-model
    ├─ /api/load-data
    ├─ /api/predict
    └─ /api/available-models
    ↓
Flask 后端 (app.py)
    ├─ 数据验证
    ├─ 模型管理
    ├─ 预测执行
    └─ 结果保存
    ↓
Kronos 模型
    ├─ KronosTokenizer
    ├─ Kronos
    └─ KronosPredictor
    ↓
可视化结果 (Plotly)
    ├─ K 线图表
    ├─ 预测数据
    ├─ 实际数据对比
    └─ 误差指标
    ↓
JSON 结果保存
    └─ prediction_results/
```

---

## 6. 性能优化建议

| 优化项 | 方法 | 效果 |
|--------|------|------|
| **模型选择** | 使用 mini 或 small | ~3× 快速 |
| **设备选择** | 使用 CUDA GPU | ~10× 快速 |
| **采样次数** | 减少 sample_count | 更快预测 |
| **缓存** | 预加载模型 | 消除加载延迟 |

**生产环境推荐**：
```
模型：Kronos-small
设备：CUDA GPU (NVIDIA)
采样：1-2 次
温度：1.0
top_p：0.9
```

---

## 7. 扩展开发

### 7.1 添加新的预测参数

```python
# 在 app.py 中添加新参数
new_param = request.json.get('new_param', default_value)

# 传递给预测器
result = predictor.predict(..., new_param=new_param)

# 在 index.html 中添加 UI 控件
<input type="range" id="new-param" value="1.0" min="0" max="2">
```

### 7.2 自定义对比指标

```javascript
// 在 getPredictionQuality 中添加新指标
function getPredictionQuality(predictions, actuals) {
    // 原有指标：MAE、RMSE、MAPE

    // 添加新指标（如方向准确率）
    let directional_accuracy = 0;
    for (let i = 0; i < minLen; i++) {
        const pred_move = predictions[i].close - predictions[i].open;
        const actual_move = actuals[i].close - actuals[i].open;
        if ((pred_move > 0 && actual_move > 0) ||
            (pred_move < 0 && actual_move < 0)) {
            directional_accuracy++;
        }
    }
    directional_accuracy = (directional_accuracy / minLen) * 100;

    return { mae, rmse, mape, directional_accuracy };
}
```

### 7.3 集成更多数据源

```python
# 在 load_data_file 中添加新格式支持
def load_data_file(file_path):
    if file_path.endswith('.json'):
        df = pd.read_json(file_path)
    elif file_path.endswith('.xlsx'):
        df = pd.read_excel(file_path)
    elif file_path.endswith('.sqlite'):
        df = pd.read_sql(..., file_path)
    # ...
```

---

## 总结

WebUI 模块通过以下特点提供了完整的交互式预测界面：

1. **用户友好**：直观的操作流程，无需编程
2. **灵活参数**：支持多种预测参数调整
3. **实时反馈**：即时的预测结果和对比分析
4. **自动保存**：所有预测结果自动持久化
5. **多设备支持**：CPU/GPU 灵活选择
6. **模型多样性**：三种不同规模的模型可选
7. **可视化强大**：交互式 K 线图和详细对比表

使用 WebUI，用户可以轻松进行 Kronos 模型的预测，无需深入了解底层实现细节。

---

## 8. 功能分析与增强建议

### 8.1 当前功能清单

#### ✅ 已实现的核心功能

| 功能 | 实现位置 | 状态 |
|------|---------|------|
| 模型加载 (3 种规模) | `app.py:626-663` | ✅ 完整 |
| 数据加载 (CSV/Feather) | `app.py:341-402` | ✅ 完整 |
| 时间窗口滑块 | `index.html:510-532` | ✅ 完整 |
| K 线图可视化 | `app.py:209-328` | ✅ 完整 |
| 预测执行 | `app.py:404-624` | ✅ 完整 |
| 误差对比分析 | `index.html:583-631` | ✅ 完整 |
| 结果保存 (JSON) | `app.py:125-207` | ✅ 完整 |
| 温度/采样参数 | `index.html:547-566` | ✅ 完整 |
| 多模型支持 | `app.py:33-58` | ✅ 完整 |
| 多设备支持 (CPU/GPU/MPS) | `index.html:462-469` | ✅ 完整 |

---

### 8.2 缺失功能分析

#### 🔴 优先级高 - 强烈建议实现

##### 1. 批量预测功能 (Batch Prediction)

**当前状态**：仅支持单个文件单次预测

**需求**：
- 支持多文件同时加载和预测
- 支持参数组合预设
- 后台队列处理
- 实时进度反馈

**实现复杂度**：⭐⭐⭐ (中等)
**业务价值**：🎯 高 (大幅提升效率)

**建议实现位置**：
```
webui/
├── app.py
│   ├── 新增: @app.route('/api/batch-predict', methods=['POST'])
│   ├── 新增: class BatchTaskManager
│   └── 新增: def process_batch_predictions(task_queue)
├── static/ (新增目录)
│   ├── batch_predictions.js
│   └── queue_manager.js
└── templates/
    └── 新增: batch_prediction.html
```

**核心代码框架**：
```python
@app.route('/api/batch-predict', methods=['POST'])
def batch_predict():
    """批量预测端点"""
    files = request.json.get('files')  # 文件列表
    params_list = request.json.get('params_list')  # 参数组合

    # 创建任务队列并后台处理
    task_id = create_batch_task(files, params_list)
    return jsonify({'task_id': task_id, 'status': 'queued'})

@app.route('/api/batch-status/<task_id>', methods=['GET'])
def get_batch_status(task_id):
    """获取批量预测进度"""
    return jsonify(batch_tasks[task_id])
```

---

##### 2. 预测历史管理 (Prediction History)

**当前状态**：预测结果存为 JSON，无集中管理

**需求**：
- SQLite 数据库存储
- 历史查询和过滤
- 版本控制和对比
- 标签和备注系统

**实现复杂度**：⭐⭐ (简单)
**业务价值**：🎯 高 (知识库积累)

**建议架构**：
```python
# database.py (新增)
class PredictionRecord(Base):
    __tablename__ = 'predictions'

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    model_used = Column(String)
    data_file = Column(String)
    mae = Column(Float)
    rmse = Column(Float)
    mape = Column(Float)
    tags = Column(String)  # 用户标签
    notes = Column(String)
```

---

##### 3. 模型对比分析 (Model Comparison)

**当前状态**：一次只能加载一个模型

**需求**：
- 同时加载多个模型
- 相同数据下性能对比
- 性能排名和推荐

**实现复杂度**：⭐⭐⭐ (中等)
**业务价值**：🎯 高 (快速选择最优模型)

**新端点**：
```python
@app.route('/api/compare-models', methods=['POST'])
def compare_models():
    """对比多个模型"""
    model_keys = request.json.get('model_keys')
    file_path = request.json.get('file_path')

    # 加载并预测，返回并排对比结果
    return jsonify({'metrics': metrics, 'ranked': ranked_models})
```

---

#### 🟡 优先级中 - 建议后续实现

##### 4. 高级可视化 (Advanced Visualization)

**增强建议**：
- 多种图表支持（蜡烛图、折线图、柱状图）
- 技术指标叠加（MA、BB、RSI）
- 置信度区间显示
- 交互式注释

**实现复杂度**：⭐⭐⭐⭐ (较复杂)
**业务价值**：🎯 中 (用户体验增强)

---

##### 5. 性能监控面板 (Performance Dashboard)

**需求**：
- 实时资源使用（CPU、内存、GPU）
- 预测延迟统计
- 吞吐量监控
- 模型推理时间分布

**实现复杂度**：⭐⭐⭐ (中等)
**业务价值**：🎯 中 (系统健康度监控)

---

##### 6. 数据预处理工具 (Data Preprocessing)

**需求**：
- 缺失值填充
- 异常值检测
- 标准化选项
- 特征工程助手

**实现复杂度**：⭐⭐ (简单)
**业务价值**：🎯 中 (数据质量提升)

---

##### 11. 回测框架 (Backtesting Framework)

**需求**：
- 基于预测结果的策略回测
- 多种交易策略支持
- 风险指标计算 (Sharpe、Sortino、最大回撤)
- 对比基准收益

**实现复杂度**：⭐⭐⭐⭐⭐ (最复杂)
**业务价值**：🎯 高 (量化预测可用性)

**建议模块**：
```
webui/backtest/
├── __init__.py
├── engine.py      # 回测引擎
├── strategies.py  # 策略库
└── metrics.py     # 风险指标
```

---

#### 🟢 优先级低 - 可选增强

##### 8. 结果导出 (Export Results)
- CSV、Excel、PDF 导出
- 报告生成

##### 9. 实时通知 (Notifications)
- WebSocket 推送
- 任务完成提醒

##### 10. API 文档 (API Documentation)
- Swagger/OpenAPI 集成
- 交互式 API 测试

---

### 8.3 功能优先级矩阵

```
┌──────────────────┬──────────┬──────────┐
│ 优先级 │ 影响度 │ 复杂度 │
├──────────────────┼──────────┼──────────┤
│ 🔴 高   │ 🎯 高  │ ⭐⭐⭐   │
│ 🟡 中   │ 🎯 中  │ ⭐⭐⭐⭐ │
│ 🟢 低   │ 🎯 低  │ ⭐⭐    │
└──────────────────┴──────────┴──────────┘

建议实现序列:

第 1 迭代 (2-3 周)
  ↓ 批量预测
  ↓ 预测历史管理
  ↓ 结果导出

第 2 迭代 (3-4 周)
  ↓ 模型对比分析
  ↓ 高级可视化
  ↓ 性能监控

第 3 迭代 (4-5 周)
  ↓ 数据预处理工具
  ↓ 回测框架
  ↓ 数据集管理器

第 4 迭代 (持续)
  ↓ 参数自动优化
  ↓ 实时通知系统
  ↓ API 文档/SDK
```

---

### 8.4 技术选型建议

**后端增强**：
- SQLAlchemy (ORM 数据库)
- Celery (异步任务队列)
- Redis (缓存和消息队列)
- APScheduler (定时任务)
- Prometheus (性能监控)

**前端增强**：
- Vue.js 或 React (组件化框架)
- ECharts (高级可视化)
- WebSocket (实时通信)
- Tailwind CSS (样式框架)

---

### 8.5 总体建议

当前 WebUI 已具备完整的基础预测功能。建议优先实现以下三个功能来快速增加业务价值：

1. **批量预测** → 提升用户效率
2. **预测历史** → 知识库积累
3. **模型对比** → 智能决策支持

这些功能特点：
- ✅ 直接服务于用户
- ✅ 使用现有架构可实现
- ✅ 2-3 周内可完成
- ✅ 便于收集用户反馈

后续逐步增加高级分析和自动化功能，最终形成完整的**金融预测分析平台**。

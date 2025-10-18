import os
import pandas as pd
import numpy as np
import json
import plotly.graph_objects as go
import plotly.utils
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import sys
import warnings
import datetime
import ccxt
from tqdm import tqdm
warnings.filterwarnings('ignore')

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from model import Kronos, KronosTokenizer, KronosPredictor
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    print("Warning: Kronos model cannot be imported, will use simulated data for demonstration")

app = Flask(__name__)
CORS(app)

# Global variables to store models
tokenizer = None
model = None
predictor = None

# Available model configurations
AVAILABLE_MODELS = {
    'kronos-mini': {
        # 'name': 'Kronos-mini',
        # 使用中文
        'name': "mini版",
        'model_id': 'NeoQuasar/Kronos-mini',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-2k',
        'context_length': 2048,
        'params': '4.1M',
        'description': '轻量级模型，适合快速预测'
    },
    'kronos-small': {
        # 'name': 'Kronos-small',
        'name': 'small版',
        'model_id': 'NeoQuasar/Kronos-small',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '24.7M',
        'description': '小型模型，平衡性能和速度'
    },
    'kronos-base': {
        # 'name': 'Kronos-base',
        'name': 'base版',
        'model_id': 'NeoQuasar/Kronos-base',
        'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
        'context_length': 512,
        'params': '102.3M',
        'description': '基础模型，提供更好的预测质量'
    },
    # 'Kronos-large': {
    #     'name': 'Kronos-large',
    #     'model_id': 'NeoQuasar/Kronos-large',
    #     'tokenizer_id': 'NeoQuasar/Kronos-Tokenizer-base',
    #     'context_length': 512,
    #     'params': '499.2M',
    #     'description': 'Large model, provides better prediction quality'
    # }
}

def fetch_and_save_ohlcv(symbol, timeframe, data_points=350):
    """
    从 Binance 获取指定交易对和时间段的 OHLCV 数据，
    将其保存为 CSV 文件，并返回 DataFrame。
    """
    try:
        # 使用 Binance 交易所
        exchange = ccxt.binance()

        # 构建永续合约的交易对符号（Binance 格式）
        symbol_upper = f"{symbol.upper()}USDT"

        print(f"正在从 Binance 获取 {symbol_upper} {timeframe} 数据...")

        limit_per_call = 1000  # Binance 的限制
        all_ohlcv = []
        since = None

        while len(all_ohlcv) < data_points:
            try:
                # Binance 的 fetch_ohlcv 调用
                ohlcv = exchange.fetch_ohlcv(symbol_upper, timeframe, since=since, limit=limit_per_call)
            except ccxt.BaseError as e:
                return None, f"获取数据失败: {str(e)}。请检查交易对 '{symbol_upper}' 和时间周期 '{timeframe}' 是否有效"

            if not ohlcv:
                print(f"无法获取更多数据。可能已到达 {symbol_upper} 历史数据的开始。")
                break

            all_ohlcv = ohlcv + all_ohlcv
            since = ohlcv[0][0]

        final_ohlcv = all_ohlcv[-data_points:]

        if not final_ohlcv:
            return None, "未检索到任何数据。请检查您的输入"

        df = pd.DataFrame(final_ohlcv, columns=['timestamps', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamps'] = pd.to_datetime(df['timestamps'], unit='ms')

        # 确保 data 目录存在
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
        os.makedirs(data_dir, exist_ok=True)

        file_path = os.path.join(data_dir, f"{symbol.lower()}_{timeframe}.csv")
        df.to_csv(file_path, index=False)

        print(f"成功获取并保存 {len(final_ohlcv)} 个 K 线数据点到 {file_path}")

        return df, None

    except Exception as e:
        return None, f"下载数据时出错: {str(e)}"

def load_data_files():
    """Scan data directory and return available data files"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    data_files = []

    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith(('.csv', '.feather')):
                file_path = os.path.join(data_dir, file)
                file_size = os.path.getsize(file_path)
                data_files.append({
                    'name': file,
                    'path': file_path,
                    'size': f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.1f} MB"
                })

    return data_files

def load_data_file(file_path):
    """Load data file"""
    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.feather'):
            df = pd.read_feather(file_path)
        else:
            return None, "不支持的文件格式"
        
        # Check required columns
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            return None, f"缺少必需的列: {required_cols}"
        
        # Process timestamp column
        if 'timestamps' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamps'])
        elif 'timestamp' in df.columns:
            df['timestamps'] = pd.to_datetime(df['timestamp'])
        elif 'date' in df.columns:
            # If column name is 'date', rename it to 'timestamps'
            df['timestamps'] = pd.to_datetime(df['date'])
        else:
            # If no timestamp column exists, create one
            df['timestamps'] = pd.date_range(start='2024-01-01', periods=len(df), freq='1H')
        
        # Ensure numeric columns are numeric type
        for col in ['open', 'high', 'low', 'close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Process volume column (optional)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        # Process amount column (optional, but not used for prediction)
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
        
        # Remove rows containing NaN values
        df = df.dropna()
        
        return df, None
        
    except Exception as e:
        return None, f"加载文件失败: {str(e)}"

def save_prediction_results(file_path, prediction_type, prediction_results, actual_data, input_data, prediction_params):
    """Save prediction results to file"""
    try:
        # Create prediction results directory
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prediction_results')
        os.makedirs(results_dir, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'prediction_{timestamp}.json'
        filepath = os.path.join(results_dir, filename)
        
        # Prepare data for saving
        save_data = {
            'timestamp': datetime.datetime.now().isoformat(),
            'file_path': file_path,
            'prediction_type': prediction_type,
            'prediction_params': prediction_params,
            'input_data_summary': {
                'rows': len(input_data),
                'columns': list(input_data.columns),
                'price_range': {
                    'open': {'min': float(input_data['open'].min()), 'max': float(input_data['open'].max())},
                    'high': {'min': float(input_data['high'].min()), 'max': float(input_data['high'].max())},
                    'low': {'min': float(input_data['low'].min()), 'max': float(input_data['low'].max())},
                    'close': {'min': float(input_data['close'].min()), 'max': float(input_data['close'].max())}
                },
                'last_values': {
                    'open': float(input_data['open'].iloc[-1]),
                    'high': float(input_data['high'].iloc[-1]),
                    'low': float(input_data['low'].iloc[-1]),
                    'close': float(input_data['close'].iloc[-1])
                }
            },
            'prediction_results': prediction_results,
            'actual_data': actual_data,
            'analysis': {}
        }
        
        # If actual data exists, perform comparison analysis
        if actual_data and len(actual_data) > 0:
            # Calculate continuity analysis
            if len(prediction_results) > 0 and len(actual_data) > 0:
                last_pred = prediction_results[0]  # First prediction point
            first_actual = actual_data[0]      # First actual point
                
            save_data['analysis']['continuity'] = {
                    'last_prediction': {
                        'open': last_pred['open'],
                        'high': last_pred['high'],
                        'low': last_pred['low'],
                        'close': last_pred['close']
                    },
                    'first_actual': {
                        'open': first_actual['open'],
                        'high': first_actual['high'],
                        'low': first_actual['low'],
                        'close': first_actual['close']
                    },
                    'gaps': {
                        'open_gap': abs(last_pred['open'] - first_actual['open']),
                        'high_gap': abs(last_pred['high'] - first_actual['high']),
                        'low_gap': abs(last_pred['low'] - first_actual['low']),
                        'close_gap': abs(last_pred['close'] - first_actual['close'])
                    },
                    'gap_percentages': {
                        'open_gap_pct': (abs(last_pred['open'] - first_actual['open']) / first_actual['open']) * 100,
                        'high_gap_pct': (abs(last_pred['high'] - first_actual['high']) / first_actual['high']) * 100,
                        'low_gap_pct': (abs(last_pred['low'] - first_actual['low']) / first_actual['low']) * 100,
                        'close_gap_pct': (abs(last_pred['close'] - first_actual['close']) / first_actual['close']) * 100
                    }
                }
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        
        print(f"预测结果已保存到: {filepath}")
        return filepath
        
    except Exception as e:
        print(f"保存预测结果失败: {e}")
        return None

def create_prediction_chart(df, pred_df, lookback, pred_len, actual_df=None, historical_start_idx=0):
    """Create prediction chart"""
    # Use specified historical data start position, not always from the beginning of df
    if historical_start_idx + lookback + pred_len <= len(df):
        # Display lookback historical points + pred_len prediction points starting from specified position
        historical_df = df.iloc[historical_start_idx:historical_start_idx+lookback]
        prediction_range = range(historical_start_idx+lookback, historical_start_idx+lookback+pred_len)
    else:
        # If data is insufficient, adjust to maximum available range
        available_lookback = min(lookback, len(df) - historical_start_idx)
        available_pred_len = min(pred_len, max(0, len(df) - historical_start_idx - available_lookback))
        historical_df = df.iloc[historical_start_idx:historical_start_idx+available_lookback]
        prediction_range = range(historical_start_idx+available_lookback, historical_start_idx+available_lookback+available_pred_len)
    
    # Create chart
    fig = go.Figure()
    
    # Add historical data (candlestick chart)
    fig.add_trace(go.Candlestick(
        x=historical_df['timestamps'] if 'timestamps' in historical_df.columns else historical_df.index,
        open=historical_df['open'],
        high=historical_df['high'],
        low=historical_df['low'],
        close=historical_df['close'],
        name='历史数据（400个数据点）',
        increasing_line_color='#26A69A',
        decreasing_line_color='#EF5350'
    ))
    
    # Add prediction data (candlestick chart)
    if pred_df is not None and len(pred_df) > 0:
        # Calculate prediction data timestamps - ensure continuity with historical data
        if 'timestamps' in df.columns and len(historical_df) > 0:
            # Start from the last timestamp of historical data, create prediction timestamps with the same time interval
            last_timestamp = historical_df['timestamps'].iloc[-1]
            time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0] if len(df) > 1 else pd.Timedelta(hours=1)
            
            pred_timestamps = pd.date_range(
                start=last_timestamp + time_diff,
                periods=len(pred_df),
                freq=time_diff
            )
        else:
            # If no timestamps, use index
            pred_timestamps = range(len(historical_df), len(historical_df) + len(pred_df))
        
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
    
    # Add actual data for comparison (if exists)
    if actual_df is not None and len(actual_df) > 0:
        # Actual data should be in the same time period as prediction data
        if 'timestamps' in df.columns:
            # Actual data should use the same timestamps as prediction data to ensure time alignment
            if 'pred_timestamps' in locals():
                actual_timestamps = pred_timestamps
            else:
                # If no prediction timestamps, calculate from the last timestamp of historical data
                if len(historical_df) > 0:
                    last_timestamp = historical_df['timestamps'].iloc[-1]
                    time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0] if len(df) > 1 else pd.Timedelta(hours=1)
                    actual_timestamps = pd.date_range(
                        start=last_timestamp + time_diff,
                        periods=len(actual_df),
                        freq=time_diff
                    )
                else:
                    actual_timestamps = range(len(historical_df), len(historical_df) + len(actual_df))
        else:
            actual_timestamps = range(len(historical_df), len(historical_df) + len(actual_df))
        
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
    
    # Update layout
    fig.update_layout(
        title='Kronos 金融预测结果 - 400 个历史数据点 + 120 个预测点 vs 120 个实际数据点',
        xaxis_title='时间',
        yaxis_title='价格',
        template='plotly_white',
        height=600,
        showlegend=True
    )
    
    # Ensure x-axis time continuity
    if 'timestamps' in historical_df.columns:
        # Get all timestamps and sort them
        all_timestamps = []
        if len(historical_df) > 0:
            all_timestamps.extend(historical_df['timestamps'])
        if 'pred_timestamps' in locals():
            all_timestamps.extend(pred_timestamps)
        if 'actual_timestamps' in locals():
            all_timestamps.extend(actual_timestamps)
        
        if all_timestamps:
            all_timestamps = sorted(all_timestamps)
            fig.update_xaxes(
                range=[all_timestamps[0], all_timestamps[-1]],
                rangeslider_visible=False,
                type='date'
            )
    
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/data-files')
def get_data_files():
    """获取可用数据文件列表"""
    data_files = load_data_files()
    return jsonify(data_files)

@app.route('/api/load-data', methods=['POST'])
def load_data():
    """加载数据文件"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')

        if not file_path:
            return jsonify({'error': '文件路径不能为空'}), 400
        
        df, error = load_data_file(file_path)
        if error:
            return jsonify({'error': error}), 400
        
        # Detect data time frequency
        def detect_timeframe(df):
            if len(df) < 2:
                return "未知"
            
            time_diffs = []
            for i in range(1, min(10, len(df))):  # Check first 10 time differences
                diff = df['timestamps'].iloc[i] - df['timestamps'].iloc[i-1]
                time_diffs.append(diff)
            
            if not time_diffs:
                return "未知"
            
            # Calculate average time difference
            avg_diff = sum(time_diffs, pd.Timedelta(0)) / len(time_diffs)
            
            # Convert to readable format
            if avg_diff < pd.Timedelta(minutes=1):
                return f"{avg_diff.total_seconds():.0f} seconds"
            elif avg_diff < pd.Timedelta(hours=1):
                return f"{avg_diff.total_seconds() / 60:.0f} minutes"
            elif avg_diff < pd.Timedelta(days=1):
                return f"{avg_diff.total_seconds() / 3600:.0f} hours"
            else:
                return f"{avg_diff.days} days"
        
        # Return data information
        data_info = {
            'rows': len(df),
            'columns': list(df.columns),
            'start_date': df['timestamps'].min().isoformat() if 'timestamps' in df.columns else 'N/A',
            'end_date': df['timestamps'].max().isoformat() if 'timestamps' in df.columns else 'N/A',
            'price_range': {
                'min': float(df[['open', 'high', 'low', 'close']].min().min()),
                'max': float(df[['open', 'high', 'low', 'close']].max().max())
            },
            'prediction_columns': ['open', 'high', 'low', 'close'] + (['volume'] if 'volume' in df.columns else []),
            'timeframe': detect_timeframe(df)
        }
        
        return jsonify({
            'success': True,
            'data_info': data_info,
            'message': f'成功加载数据，共 {len(df)} 行'
        })

    except Exception as e:
        return jsonify({'error': f'加载数据失败: {str(e)}'}), 500

@app.route('/api/predict', methods=['POST'])
def predict():
    """执行预测"""
    global predictor, model, tokenizer, MODEL_AVAILABLE

    # 详细的诊断日志
    print(f"\n{'='*80}")
    print(f"[预测请求] 接收到预测请求")
    print(f"[诊断] MODEL_AVAILABLE: {MODEL_AVAILABLE}")
    print(f"[诊断] predictor 状态: {predictor}")
    print(f"[诊断] model 状态: {model}")
    print(f"[诊断] tokenizer 状态: {tokenizer}")
    print(f"{'='*80}\n")

    try:
        data = request.get_json()
        file_path = data.get('file_path')
        lookback = int(data.get('lookback', 400))
        pred_len = int(data.get('pred_len', 120))
        
        # Get prediction quality parameters
        temperature = float(data.get('temperature', 1.0))
        top_p = float(data.get('top_p', 0.9))
        sample_count = int(data.get('sample_count', 1))
        
        if not file_path:
            return jsonify({'error': '文件路径不能为空'}), 400

        # Load data
        df, error = load_data_file(file_path)
        if error:
            return jsonify({'error': error}), 400

        if len(df) < lookback:
            return jsonify({'error': f'数据长度不足，需要至少 {lookback} 行'}), 400

        # Perform prediction - with comprehensive diagnostics
        print(f"\n[检查] 准备执行预测...")
        print(f"[检查] 请求编号: {id(request)}")  # 用来追踪请求

        if not MODEL_AVAILABLE:
            error_msg = '❌ Kronos 模型库不可用，请检查依赖安装'
            print(f"[错误] {error_msg}")
            return jsonify({'error': error_msg}), 400

        if predictor is None:
            error_msg = '❌ 预测器未初始化。请先加载模型！\n' \
                       f'   MODEL_AVAILABLE={MODEL_AVAILABLE}\n' \
                       f'   predictor={predictor}\n' \
                       f'   model={model}\n' \
                       f'   tokenizer={tokenizer}'
            print(f"[错误] {error_msg}")
            return jsonify({'error': error_msg}), 400

        print(f"[检查] predictor 对象有效: {predictor is not None}")

        try:
            print(f"[执行] 开始 Kronos 模型预测...")
            # Use real Kronos model
            # Only use necessary columns: OHLCV, excluding amount
            required_cols = ['open', 'high', 'low', 'close']
            if 'volume' in df.columns:
                required_cols.append('volume')

            print(f"[检查] 数据文件列: {df.columns.tolist()}")
            print(f"[检查] 使用的列: {required_cols}")

            # Process time period selection
            start_date = data.get('start_date')

            if start_date:
                print(f"[检查] 自定义时间范围: 从 {start_date} 开始")
                # Custom time period - fix logic: use data within selected window
                start_dt = pd.to_datetime(start_date)

                # Check if start_date is before data starts
                data_start = df['timestamps'].min()
                data_end = df['timestamps'].max()
                print(f"[检查] 数据时间范围: {data_start} 到 {data_end}")
                print(f"[检查] 请求时间: {start_dt}")

                if start_dt < data_start:
                    error_msg = f'❌ 选择的起始时间 ({start_dt.strftime("%Y-%m-%d %H:%M")}) 早于数据的最早时间 ({data_start.strftime("%Y-%m-%d %H:%M")})。请选择 {data_start.strftime("%Y-%m-%d %H:%M")} 或之后的时间。'
                    print(f"[错误] {error_msg}")
                    return jsonify({'error': error_msg}), 400

                # Find data after start time
                mask = df['timestamps'] >= start_dt
                time_range_df = df[mask]

                print(f"[检查] 从 {start_dt} 后筛选数据: {len(time_range_df)} 行")

                # Ensure sufficient data: lookback + pred_len
                if len(time_range_df) < lookback + pred_len:
                    error_msg = f'❌ 从起始时间 {start_dt.strftime("%Y-%m-%d %H:%M")} 开始数据不足。需要至少 {lookback + pred_len} 个数据点，当前仅有 {len(time_range_df)} 个。建议选择更早的时间或使用数据量更大的文件。'
                    print(f"[错误] {error_msg}")
                    return jsonify({'error': error_msg}), 400

                # Use first lookback data points within selected window for prediction
                x_df = time_range_df.iloc[:lookback][required_cols]
                x_timestamp = time_range_df.iloc[:lookback]['timestamps']

                # Use last pred_len data points within selected window as actual values
                y_timestamp = time_range_df.iloc[lookback:lookback+pred_len]['timestamps']

                # Calculate actual time period length
                start_timestamp = time_range_df['timestamps'].iloc[0]
                end_timestamp = time_range_df['timestamps'].iloc[lookback+pred_len-1]
                time_span = end_timestamp - start_timestamp

                prediction_type = f"Kronos 模型预测（在选定窗口内：前 {lookback} 个数据点用于预测，后 {pred_len} 个数据点用于对比，时间跨度：{time_span}）"
            else:
                print(f"[检查] 使用最新数据进行预测")
                # Use latest data
                x_df = df.iloc[:lookback][required_cols]
                x_timestamp = df.iloc[:lookback]['timestamps']
                y_timestamp = df.iloc[lookback:lookback+pred_len]['timestamps']
                prediction_type = "Kronos 模型预测（最新数据）"

            print(f"[检查] 输入数据形状: {x_df.shape}")

            # Ensure timestamps are Series format, not DatetimeIndex, to avoid .dt attribute error in Kronos model
            if isinstance(x_timestamp, pd.DatetimeIndex):
                x_timestamp = pd.Series(x_timestamp, name='timestamps')
            if isinstance(y_timestamp, pd.DatetimeIndex):
                y_timestamp = pd.Series(y_timestamp, name='timestamps')

            print(f"[执行] 调用 predictor.predict()...")
            print(f"        - lookback={lookback}, pred_len={pred_len}")
            print(f"        - temperature={temperature}, top_p={top_p}, sample_count={sample_count}")

            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=sample_count
            )

            print(f"[成功] 预测完成，输出形状: {pred_df.shape}")

        except Exception as e:
            import traceback
            error_msg = f'Kronos 模型预测失败: {str(e)}'
            print(f"\n[错误] {error_msg}")
            print(f"[错误] 异常类型: {type(e).__name__}")
            print(f"[堆栈跟踪]:\n{traceback.format_exc()}")

            # 返回更详细的错误信息便于前端调试
            return jsonify({
                'error': error_msg,
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc()
            }), 500
        
        # Prepare actual data for comparison (if exists)
        actual_data = []
        actual_df = None
        
        if start_date:  # Custom time period
            # Fix logic: use data within selected window
            # Prediction uses first 400 data points within selected window
            # Actual data should be last 120 data points within selected window
            start_dt = pd.to_datetime(start_date)
            
            # Find data starting from start_date
            mask = df['timestamps'] >= start_dt
            time_range_df = df[mask]
            
            if len(time_range_df) >= lookback + pred_len:
                # Get last 120 data points within selected window as actual values
                actual_df = time_range_df.iloc[lookback:lookback+pred_len]
                
                for i, (_, row) in enumerate(actual_df.iterrows()):
                    actual_data.append({
                        'timestamp': row['timestamps'].isoformat(),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']) if 'volume' in row else 0,
                        'amount': float(row['amount']) if 'amount' in row else 0
                    })
        else:  # Latest data
            # Prediction uses first 400 data points
            # Actual data should be 120 data points after first 400 data points
            if len(df) >= lookback + pred_len:
                actual_df = df.iloc[lookback:lookback+pred_len]
                for i, (_, row) in enumerate(actual_df.iterrows()):
                    actual_data.append({
                        'timestamp': row['timestamps'].isoformat(),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']) if 'volume' in row else 0,
                        'amount': float(row['amount']) if 'amount' in row else 0
                    })
        
        # Create chart - pass historical data start position
        if start_date:
            # Custom time period: find starting position of historical data in original df
            start_dt = pd.to_datetime(start_date)
            mask = df['timestamps'] >= start_dt
            historical_start_idx = df[mask].index[0] if len(df[mask]) > 0 else 0
        else:
            # Latest data: start from beginning
            historical_start_idx = 0
        
        chart_json = create_prediction_chart(df, pred_df, lookback, pred_len, actual_df, historical_start_idx)
        
        # Prepare prediction result data - fix timestamp calculation logic
        if 'timestamps' in df.columns:
            if start_date:
                # Custom time period: use selected window data to calculate timestamps
                start_dt = pd.to_datetime(start_date)
                mask = df['timestamps'] >= start_dt
                time_range_df = df[mask]
                
                if len(time_range_df) >= lookback:
                    # Calculate prediction timestamps starting from last time point of selected window
                    last_timestamp = time_range_df['timestamps'].iloc[lookback-1]
                    time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0]
                    future_timestamps = pd.date_range(
                        start=last_timestamp + time_diff,
                        periods=pred_len,
                        freq=time_diff
                    )
                else:
                    future_timestamps = []
            else:
                # Latest data: calculate from last time point of entire data file
                last_timestamp = df['timestamps'].iloc[-1]
                time_diff = df['timestamps'].iloc[1] - df['timestamps'].iloc[0]
                future_timestamps = pd.date_range(
                    start=last_timestamp + time_diff,
                    periods=pred_len,
                    freq=time_diff
                )
        else:
            future_timestamps = range(len(df), len(df) + pred_len)
        
        prediction_results = []
        for i, (_, row) in enumerate(pred_df.iterrows()):
            prediction_results.append({
                'timestamp': future_timestamps[i].isoformat() if i < len(future_timestamps) else f"T{i}",
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']) if 'volume' in row else 0,
                'amount': float(row['amount']) if 'amount' in row else 0
            })
        
        # Save prediction results to file
        try:
            save_prediction_results(
                file_path=file_path,
                prediction_type=prediction_type,
                prediction_results=prediction_results,
                actual_data=actual_data,
                input_data=x_df,
                prediction_params={
                    'lookback': lookback,
                    'pred_len': pred_len,
                    'temperature': temperature,
                    'top_p': top_p,
                    'sample_count': sample_count,
                    'start_date': start_date if start_date else 'latest'
                }
            )
        except Exception as e:
            print(f"Failed to save prediction results: {e}")
        
        return jsonify({
            'success': True,
            'prediction_type': prediction_type,
            'chart': chart_json,
            'prediction_results': prediction_results,
            'actual_data': actual_data,
            'has_comparison': len(actual_data) > 0,
            'message': f'预测完成，生成 {pred_len} 个预测点' + (f'，包含 {len(actual_data)} 个实际数据点用于对比' if len(actual_data) > 0 else '')
        })

    except Exception as e:
        return jsonify({'error': f'预测失败: {str(e)}'}), 500

@app.route('/api/load-model', methods=['POST'])
def load_model():
    """加载 Kronos 模型"""
    global tokenizer, model, predictor

    try:
        if not MODEL_AVAILABLE:
            return jsonify({'error': 'Kronos 模型库不可用'}), 400

        data = request.get_json()
        model_key = data.get('model_key', 'kronos-small')
        device = data.get('device', 'cpu')

        if model_key not in AVAILABLE_MODELS:
            return jsonify({'error': f'不支持的模型: {model_key}'}), 400
        
        model_config = AVAILABLE_MODELS[model_key]
        
        # Load tokenizer and model
        tokenizer = KronosTokenizer.from_pretrained(model_config['tokenizer_id'])
        model = Kronos.from_pretrained(model_config['model_id'])
        
        # Create predictor
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=model_config['context_length'])
        
        return jsonify({
            'success': True,
            'message': f'模型加载成功: {model_config["name"]} ({model_config["params"]}) 在 {device}',
            'model_info': {
                'name': model_config['name'],
                'params': model_config['params'],
                'context_length': model_config['context_length'],
                'description': model_config['description']
            }
        })

    except Exception as e:
        return jsonify({'error': f'模型加载失败: {str(e)}'}), 500

@app.route('/api/available-models')
def get_available_models():
    """获取可用模型列表"""
    return jsonify({
        'models': AVAILABLE_MODELS,
        'model_available': MODEL_AVAILABLE
    })

@app.route('/api/model-status')
def get_model_status():
    """获取模型状态"""
    if MODEL_AVAILABLE:
        if predictor is not None:
            return jsonify({
                'available': True,
                'loaded': True,
                'message': 'Kronos 模型已加载且可用',
                'current_model': {
                    'name': predictor.model.__class__.__name__,
                    'device': str(next(predictor.model.parameters()).device)
                }
            })
        else:
            return jsonify({
                'available': True,
                'loaded': False,
                'message': 'Kronos 模型可用但未加载'
            })
    else:
        return jsonify({
            'available': False,
            'loaded': False,
            'message': 'Kronos 模型库不可用，请安装相关依赖'
        })

@app.route('/api/download-data', methods=['POST'])
def download_data():
    """从 Binance 下载 OHLCV 数据"""
    try:
        data = request.get_json()
        symbol = data.get('symbol', '').strip()
        timeframe = data.get('timeframe', '').strip()
        data_points = int(data.get('data_points', 350))

        # 验证输入
        if not symbol:
            return jsonify({'error': '交易对符号不能为空'}), 400
        if not timeframe:
            return jsonify({'error': '时间周期不能为空'}), 400

        # 验证时间周期格式
        valid_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1M']
        if timeframe not in valid_timeframes:
            return jsonify({'error': f'无效的时间周期。支持的周期: {", ".join(valid_timeframes)}'}), 400

        print(f"开始下载数据: {symbol.upper()} {timeframe}")

        # 调用下载函数
        df, error = fetch_and_save_ohlcv(symbol, timeframe, data_points)

        if error:
            return jsonify({'error': error}), 500

        if df is None:
            return jsonify({'error': '数据下载失败'}), 500

        return jsonify({
            'success': True,
            'message': f'成功下载 {len(df)} 个 K 线数据点',
            'data_info': {
                'rows': len(df),
                'start_date': df['timestamps'].min().isoformat(),
                'end_date': df['timestamps'].max().isoformat(),
                'price_range': {
                    'min': float(df['close'].min()),
                    'max': float(df['close'].max())
                },
                'file_name': f"{symbol.lower()}_{timeframe}.csv"
            }
        })

    except ValueError as e:
        return jsonify({'error': f'参数错误: {str(e)}'}), 400
    except Exception as e:
        print(f"下载数据时出错: {str(e)}")
        return jsonify({'error': f'下载失败: {str(e)}'}), 500

@app.route('/api/supported-symbols', methods=['GET'])
def get_supported_symbols():
    """获取支持的交易对列表（热门币种）"""
    supported_symbols = [
        'BTC', 'ETH', 'BNB', 'XRP', 'ADA', 'SOL', 'DOT', 'DOGE',
        'MATIC', 'AVAX', 'LINK', 'ATOM', 'NEAR', 'TRX', 'FTM'
    ]

    return jsonify({
        'symbols': supported_symbols,
        'note': '可以输入任何 Binance 支持的交易对，例如: BTC、ETH、USDC 等'
    })

@app.route('/api/supported-timeframes', methods=['GET'])
def get_supported_timeframes():
    """获取支持的时间周期列表"""
    timeframes = [
        {'value': '1m', 'label': '1 分钟'},
        {'value': '5m', 'label': '5 分钟'},
        {'value': '15m', 'label': '15 分钟'},
        {'value': '30m', 'label': '30 分钟'},
        {'value': '1h', 'label': '1 小时'},
        {'value': '4h', 'label': '4 小时'},
        {'value': '1d', 'label': '1 天'},
        {'value': '1w', 'label': '1 周'},
        {'value': '1M', 'label': '1 月'}
    ]

    return jsonify({'timeframes': timeframes})

if __name__ == '__main__':
    print("正在启动 Kronos Web UI...")
    print(f"模型可用性: {MODEL_AVAILABLE}")
    if MODEL_AVAILABLE:
        print("提示: 可以通过 /api/load-model 端点加载 Kronos 模型")
    else:
        print("提示: 将使用模拟数据进行演示")

    app.run(debug=True, host='0.0.0.0', port=7070)

#!/usr/bin/env python3
"""
Kronos Web UI startup script
"""

import os
import sys
import subprocess
import webbrowser
import time

def check_dependencies():
    """检查是否安装了依赖"""
    try:
        import flask
        import flask_cors
        import pandas
        import numpy
        import plotly
        print("✅ 所有依赖已安装")
        return True
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}")
        print("请运行: pip install -r requirements.txt")
        return False

def install_dependencies():
    """安装依赖"""
    print("正在安装依赖...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError:
        print("❌ 依赖安装失败")
        return False

def main():
    """主函数"""
    print("🚀 正在启动 Kronos Web UI...")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        print("\n自动安装依赖? (y/n): ", end="")
        if input().lower() == 'y':
            if not install_dependencies():
                return
        else:
            print("请手动安装依赖并重试")
            return

    # Check model availability
    try:
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from model import Kronos, KronosTokenizer, KronosPredictor
        print("✅ Kronos 模型库可用")
        model_available = True
    except ImportError:
        print("⚠️  Kronos 模型库不可用，将使用模拟预测")
        model_available = False

    # Start Flask application
    print("\n🌐 正在启动 Web 服务器...")

    # Set environment variables
    os.environ['FLASK_APP'] = 'app.py'
    os.environ['FLASK_ENV'] = 'development'

    # Start server
    try:
        from app import app
        print("✅ Web 服务器启动成功！")
        print(f"🌐 访问地址: http://localhost:7070")
        print("💡 提示: 按 Ctrl+C 停止服务器")

        # Auto-open browser
        time.sleep(2)
        webbrowser.open('http://localhost:7070')

        # Start Flask application
        app.run(debug=True, host='0.0.0.0', port=7070)

    except Exception as e:
        print(f"❌ 启动失败: {e}")
        print("请检查 7070 端口是否被占用")

if __name__ == "__main__":
    main()

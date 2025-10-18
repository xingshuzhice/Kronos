# WebUI 数据下载功能 - 故障排除指南

## 🔧 按钮点击没有反应的解决方案

### 问题 1：页面未完全加载

**症状**：点击任何按钮都没有反应

**解决步骤**：

1. **检查浏览器控制台是否有错误**
   - 按 `F12` 打开开发者工具
   - 点击 `Console` 标签
   - 查看是否有红色错误信息

2. **强制刷新页面**
   ```
   Ctrl + Shift + R （Windows/Linux）
   或
   Cmd + Shift + R （Mac）
   ```

3. **清除浏览器缓存**
   - 关闭浏览器
   - 重新打开
   - 访问 http://localhost:7070

---

### 问题 2：WebUI 服务器未启动

**症状**：无法访问页面或显示 "无法连接"

**解决步骤**：

1. **启动 WebUI 服务器**
   ```bash
   cd /Users/zerone/code/XingShuzc/Kronos/webui
   python run.py
   ```

2. **查看启动日志**
   - 应该显示：`Running on http://0.0.0.0:7070`
   - 如果有错误，记录错误信息

3. **检查端口是否被占用**
   ```bash
   # Mac/Linux
   lsof -i :7070

   # Windows
   netstat -ano | findstr :7070
   ```

4. **如果端口被占用，改用其他端口**
   ```bash
   # 编辑 webui/run.py 或 webui/app.py
   # 将 port=7070 改为 port=8080
   ```

---

### 问题 3：后端 API 无响应

**症状**：打开开发者工具，看到 "GET /api/data-files 404 或 500"

**解决步骤**：

1. **检查后端是否正常运行**
   - 查看启动日志中是否有错误
   - 确保 Python 依赖已安装：
   ```bash
   pip install -r /Users/zerone/code/XingShuzc/Kronos/webui/requirements.txt
   ```

2. **检查 Axios 是否能连接到后端**
   - 在浏览器控制台运行：
   ```javascript
   axios.get('/api/available-models')
       .then(r => console.log('Success:', r.data))
       .catch(e => console.log('Error:', e.message))
   ```

3. **查看服务器日志**
   - 如果后端有错误，应该在启动的终端中显示

---

### 问题 4：CCXT 或依赖库缺失

**症状**：后端服务启动成功，但点击下载时返回 500 错误

**解决步骤**：

1. **检查所有依赖是否已安装**
   ```bash
   pip install ccxt==4.5.11 tqdm==4.67.1
   ```

2. **验证依赖版本**
   ```bash
   python -c "import ccxt; print(ccxt.__version__)"
   python -c "import tqdm; print(tqdm.__version__)"
   ```

3. **重新启动 WebUI 服务**
   ```bash
   python run.py
   ```

---

### 问题 5：JavaScript 错误

**症状**：打开控制台看到类似 "downloadData is not defined" 的错误

**解决步骤**：

1. **检查 HTML 文件是否正确保存**
   ```bash
   grep -n "function downloadData" /Users/zerone/code/XingShuzc/Kronos/webui/templates/index.html
   ```

2. **验证事件绑定**
   - 在控制台运行：
   ```javascript
   document.getElementById('download-data-btn').onclick
   ```
   - 应该返回事件处理函数

3. **强制刷新并重新加载脚本**
   - 完全关闭浏览器
   - 重新打开并访问页面

---

### 问题 6：时间周期下拉菜单显示为空

**症状**：时间周期选择框没有选项

**解决步骤**：

1. **检查 HTML 中的选项是否存在**
   ```bash
   grep -A 10 'id="download-timeframe"' /Users/zerone/code/XingShuzc/Kronos/webui/templates/index.html
   ```

2. **确保选项有正确的值**
   - 每个 `<option>` 标签应该有 `value` 属性
   - 示例：`<option value="1h">1 小时</option>`

---

## 📋 快速诊断清单

使用此清单来快速诊断问题：

- [ ] WebUI 服务器正在运行（终端显示 "Running on..."）
- [ ] 可以访问 http://localhost:7070
- [ ] 页面完全加载（右下角没有加载指示符）
- [ ] 浏览器控制台没有 JavaScript 错误
- [ ] 依赖库已安装（ccxt, tqdm）
- [ ] 所有按钮 ID 在 HTML 中正确定义
- [ ] 事件监听器已正确绑定

---

## 🔍 详细诊断步骤

### 步骤 1：查看浏览器控制台

1. 按 `F12` 打开开发者工具
2. 点击 `Console` 标签
3. 查找任何错误消息

**常见错误及含义**：
- `Uncaught TypeError: Cannot read property 'addEventListener' of null`
  → 按钮元素不存在或 HTML 中的 ID 不匹配

- `Failed to load resource: 404 (Not Found)`
  → API 端点不存在或服务器没有正确配置

- `Failed to fetch`
  → 网络连接问题或跨域 (CORS) 错误

### 步骤 2：检查网络请求

1. 在开发者工具中点击 `Network` 标签
2. 点击"下载数据"按钮
3. 查看请求列表中是否有到 `/api/download-data` 的 POST 请求
4. 检查请求的状态码：
   - 200 = 成功
   - 4xx = 客户端错误
   - 5xx = 服务器错误

### 步骤 3：测试后端 API

在终端中测试后端 API：

```bash
# 测试 GET 端点
curl http://localhost:7070/api/supported-symbols

# 测试 POST 端点（下载数据）
curl -X POST http://localhost:7070/api/download-data \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframe":"1h","data_points":350}'
```

---

## 💡 常见问题解答

### Q: 修改了 HTML 但看不到变化？
**A:**
1. 确保保存了文件
2. 在浏览器中按 `Ctrl + Shift + R` 强制刷新
3. 清除浏览器缓存

### Q: 下载按钮变灰色后无法恢复？
**A:**
1. 这表示请求正在进行中（最多 5-10 秒）
2. 如果一直卡住，刷新页面
3. 检查浏览器控制台中的错误

### Q: 错误信息显示后立即消失？
**A:**
1. 快速打开开发者工具控制台查看完整错误
2. 或者增加 `showDownloadStatus` 函数中的超时时间
3. 或者在浏览器控制台运行最后一个命令查看错误

---

## 🆘 如果仍然无法解决

### 收集诊断信息

请提供以下信息以获得帮助：

1. **浏览器控制台的完整错误消息**
   ```javascript
   // 在控制台中运行
   copy(document.documentElement.outerHTML)
   ```

2. **服务器启动日志**
   ```bash
   # 运行时显示的所有输出
   ```

3. **网络请求详情**
   - 打开开发者工具 → Network 标签
   - 点击下载按钮
   - 右键点击请求 → Copy as cURL

4. **系统信息**
   ```bash
   python --version
   pip list | grep -E "ccxt|flask|tqdm"
   ```

---

## 📚 相关文档

- [INTEGRATION_SUMMARY.md](./INTEGRATION_SUMMARY.md) - 功能集成总结
- [DOWNLOAD_FEATURE.md](./DOWNLOAD_FEATURE.md) - 功能详解
- [CLAUDE.md](./CLAUDE.md) - WebUI 架构文档


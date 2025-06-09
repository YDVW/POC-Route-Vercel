# Vercel Deployment Guide

## 🚀 **Deploy to Vercel**

### **Step 1: Prepare Your Repository**
Your repository is already configured for Vercel deployment with:
- `vercel.json` - Vercel configuration
- `api/index.py` - Serverless entry point
- Updated `requirements.txt` - Minimal dependencies

### **Step 2: Deploy to Vercel**

1. **Import from GitHub**:
   - Go to [vercel.com](https://vercel.com)
   - Click "New Project"
   - Import from GitHub: `https://github.com/YDVW/POC-Route.git`

2. **Configure Environment Variables**:
   - In Vercel dashboard, go to your project settings
   - Add environment variable:
     - **Name**: `OPENROUTESERVICE_API_KEY`
     - **Value**: Your OpenRouteService API key

3. **Deploy**:
   - Vercel will automatically deploy from your `main` branch
   - The app will be available at your Vercel URL

## ⚡ **Serverless Limitations**

### **What Works on Vercel**:
- ✅ CSV file upload and parsing
- ✅ Data validation and preview
- ✅ Web interface
- ✅ Basic file processing

### **What Doesn't Work on Vercel**:
- ❌ **Route optimization** (requires persistent storage)
- ❌ **Geocoding cache** (SQLite databases don't work in serverless)
- ❌ **Routing cache** (no persistent file system)
- ❌ **Long-running calculations** (serverless has time limits)

## 🔄 **Vercel vs Other Platforms**

| Feature | Vercel | Replit | Local |
|---------|--------|---------|-------|
| CSV Upload | ✅ | ✅ | ✅ |
| Route Optimization | ❌ | ✅ | ✅ |
| Caching | ❌ | ✅ | ✅ |
| Setup Complexity | Easy | Easy | Medium |
| Cost | Free | Free | Free |

## 🎯 **Recommended Use Cases**

### **Use Vercel For**:
- **Demos** and presentations
- **CSV validation** and preview
- **Landing page** for your project
- **API documentation** endpoints

### **Use Replit/Local For**:
- **Full route optimization**
- **Production use**
- **Testing with real data**
- **Development and debugging**

## 🔗 **Alternative Deployment Options**

### **For Full Functionality**:

1. **Replit** (Recommended):
   ```bash
   # Import from GitHub
   https://github.com/YDVW/POC-Route.git
   ```

2. **Local Development**:
   ```bash
   git clone https://github.com/YDVW/POC-Route.git
   cd POC-Route
   pip install -r requirements.txt
   python app.py
   ```

3. **Heroku** (with persistent storage):
   - Supports SQLite with file storage add-ons
   - Better for production use

## 🛠️ **Troubleshooting Vercel Deployment**

### **Common Issues**:

1. **Build Fails**:
   - Check if all dependencies are compatible with Python 3.9+
   - Ensure `vercel.json` is in repository root

2. **404 Errors**:
   - Verify `api/index.py` exists
   - Check routes in `vercel.json`

3. **Template Not Found**:
   - Ensure `templates/` directory is included in deployment
   - Check template paths in `api/index.py`

### **Health Check**:
Visit `/health` endpoint to verify deployment:
```json
{
  "status": "healthy",
  "message": "Route Optimizer API is running on Vercel",
  "api_key_configured": true,
  "route_optimizer_available": false
}
```

## 💡 **Next Steps**

1. **Deploy to Vercel** for demo purposes
2. **Use Replit** for full functionality
3. **Consider Heroku** for production deployment
4. **Keep local development** for testing and development 
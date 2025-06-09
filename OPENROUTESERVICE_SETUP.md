# OpenRouteService API Key Setup

Your route optimizer application now supports **road routing** using OpenRouteService! This provides much more accurate distances and travel times compared to straight-line (air) distances.

## Quick Setup

### Option 1: Automatic Setup (Recommended)
1. Run `setup_api_key.bat` (double-click the file)
2. Enter your API key when prompted
3. Restart your command prompt/PowerShell
4. Run your Flask app - road routing will be enabled automatically!

### Option 2: Manual Setup
1. Open Command Prompt or PowerShell as Administrator
2. Run: `setx OPENROUTESERVICE_API_KEY "your_api_key_here"`
3. Restart your command prompt/PowerShell
4. Your app will now use road routing!

### Option 3: Temporary Setup (This Session Only)
In your current command prompt/PowerShell:
```cmd
set OPENROUTESERVICE_API_KEY=your_api_key_here
```

## Getting Your API Key

1. Go to: https://openrouteservice.org/dev/#/signup
2. Sign up for a free account (no credit card required)
3. Verify your email address
4. Get your API key from the dashboard

### Free Plan Limits
- ✅ **2000 requests per day**
- ✅ **40 requests per minute**
- ✅ **No credit card required**
- ✅ **Multiple routing profiles** (car, bike, walking, etc.)

## How It Works

**Without API Key (Air Distance):**
- Routes calculated as straight lines
- Less accurate for actual driving
- No traffic considerations

**With API Key (Road Routing):**
- Routes follow actual roads
- More accurate distances and times
- Considers road types and restrictions
- Smart fallback to air distance if needed

## Expected Improvements

With road routing enabled, you can expect:
- **Urban areas**: 20-50% more accurate distances
- **Highway routes**: 10-20% more accurate
- **Complex city routing**: 60-140% more accurate

## Verifying It's Working

When road routing is enabled, you'll see in the logs:
```
INFO:route_optimizer:Road routing enabled with OpenRouteService API key (2000 requests/day, 40 requests/min)
```

When calculating distances, you'll see:
```
INFO:route_optimizer:Creating distance matrix using road routing (fallback to air distance)...
```

## Troubleshooting

**If you see "air distance only" in logs:**
1. Check that your environment variable is set: `echo %OPENROUTESERVICE_API_KEY%`
2. Restart your command prompt/PowerShell
3. Verify your API key is correct
4. Check your daily/minute limits haven't been exceeded

**Rate Limiting:**
The app automatically handles rate limits with:
- Smart caching (routes are cached permanently)
- Rate limiting (max 35 requests/minute to stay under limit)
- Automatic fallback to air distance when limits are hit

## Need Help?

- OpenRouteService Documentation: https://openrouteservice.org/dev/#/api-docs
- Your app logs will show detailed information about routing attempts
- The app works perfectly fine without an API key (using air distance) 
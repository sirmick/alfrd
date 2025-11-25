# ALFRD Web UI - PWA Interface

Simple Ionic PWA for mobile document capture and upload.

## Features

- 📸 Camera capture using Capacitor Camera API
- 📤 Image upload to FastAPI backend
- 🔄 Live reload development server with Vite
- 📱 Progressive Web App (installable on mobile)

## Prerequisites

- Node.js 18+ (currently using 18.19.1)
- npm

## Development

```bash
# Install dependencies (if not already done)
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

The dev server runs on **http://localhost:3000** with auto-reload.

API requests to `/api/*` are proxied to the FastAPI server at `http://localhost:8000`.

## Architecture

```
web-ui/
├── index.html          # Entry point
├── vite.config.js      # Vite configuration with API proxy
├── package.json        # Dependencies and scripts
├── public/
│   └── manifest.json   # PWA manifest
└── src/
    ├── main.jsx        # React + Ionic initialization
    ├── App.jsx         # Main app component with camera
    └── theme/
        └── variables.css  # Ionic theme variables
```

## How It Works

1. **Camera Capture**: Uses Capacitor Camera API to capture photos
2. **Base64 Conversion**: Photo is captured as base64 string
3. **Blob Upload**: Converts base64 to blob and uploads via FormData
4. **API Proxy**: Vite proxies `/api/*` to FastAPI server at `localhost:8000`
5. **Document Processing**: API creates folder in inbox for worker pool to process

## Testing

1. Start the API server: `python3 api-server/src/api_server/main.py`
2. Start the document processor: `python3 document-processor/src/document_processor/main.py`
3. Start the web UI: `npm run dev`
4. Open http://localhost:3000 in browser
5. Click "Take Photo" (or select file on desktop)
6. Click "Upload Document"
7. Check API response for document_id
8. Watch processor logs to see OCR → classification → summarization

## Mobile Testing

For full mobile testing with camera access:

```bash
# Install Capacitor CLI
npm install -g @capacitor/cli

# Initialize Capacitor (from web-ui directory)
npx cap init

# Build the app
npm run build

# Add iOS platform
npx cap add ios

# Add Android platform
npx cap add android

# Open in Xcode/Android Studio
npx cap open ios
npx cap open android
```

## API Endpoint

The PWA uploads to:
```
POST /api/v1/documents/upload-image
Content-Type: multipart/form-data

Form field: file (image file)
Returns: { document_id, status, folder, message }
```

## Browser Permissions

The Camera API requires:
- HTTPS in production (or localhost for development)
- Camera permissions granted by user
- For file upload fallback, no special permissions needed

## Next Steps

- Add document list view
- Add document detail view with structured data
- Add offline support with IndexedDB
- Add service worker for PWA installation
- Add push notifications for processing completion

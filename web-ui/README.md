# ALFRD Web UI

Ionic React PWA for document capture and viewing.

## Features

- **Camera Capture** - Take photos of documents using device camera
- **Document List** - View all processed documents with status badges
- **Document Details** - View full document information including:
  - Summary and key data
  - OCR confidence scores
  - Classification tags
  - Original document images
  - Extracted text

## Development

### Prerequisites

```bash
# Install dependencies
npm install
```

### Running Locally

```bash
# Start API server (in project root)
./scripts/start-api

# Start web UI (in web-ui directory)
npm run dev
```

The UI will be available at http://localhost:3000 and will proxy API requests to http://localhost:8000.

### Project Structure

```
web-ui/
├── src/
│   ├── App.jsx                      # Main app with routing
│   ├── main.jsx                     # Entry point
│   ├── pages/
│   │   ├── CapturePage.jsx         # Camera capture page
│   │   ├── DocumentsPage.jsx       # Document list page
│   │   └── DocumentDetailPage.jsx  # Document detail page
│   └── theme/
│       └── variables.css           # Ionic theme variables
├── public/
│   └── manifest.json               # PWA manifest
├── index.html
├── vite.config.js                  # Vite config with API proxy
└── package.json
```

## Routes

- `/` - Redirects to `/documents`
- `/documents` - List all documents
- `/documents/:id` - View document details
- `/capture` - Capture new document

## API Integration

The UI communicates with the FastAPI backend:

- `GET /api/v1/documents` - List documents
- `GET /api/v1/documents/{id}` - Get document details
- `GET /api/v1/documents/{id}/file/{filename}` - Serve document files
- `POST /api/v1/documents/upload-image` - Upload new document

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

## Notes

- Camera functionality requires HTTPS in production
- API proxy is configured for development in `vite.config.js`
- Uses Ionic Framework v8 with React

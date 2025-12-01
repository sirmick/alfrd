# Files Feature - UI Design Proposal

**Date:** 2025-12-01

---

## Overview

The Files feature provides a way to group related documents and view AI-generated summaries that span multiple documents over time. This design integrates into the existing Ionic React PWA.

---

## User Flow

```
Documents Page → "Create File" button → Select documents → Choose tags → File created
                                                                              ↓
                                                                     Files Page (new)
                                                                              ↓
                                                                   File Detail Page (new)
```

---

## Page Designs

### 1. Files Page (New)

**Route:** `/files`

**Purpose:** List all files with summaries, allow filtering by type/tags

**Layout:**
```
┌─────────────────────────────────────────────┐
│ [← Back]  Files                   [+ Create] │
├─────────────────────────────────────────────┤
│                                               │
│ 🔍 Search...              [Filter ▾]         │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📁 bill • lexus-tx-550              [>] │ │
│ │ 4 documents • Last updated: 2 days ago   │ │
│ │ Total maintenance: $934.50               │ │
│ │ Average per service: $233.63             │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📁 bill • pge • electricity         [>] │ │
│ │ 3 documents • Last updated: 1 week ago   │ │
│ │ Averaging $252.33/month                  │ │
│ │ Peak usage in September                  │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📁 school • stanford • cs-department[>] │ │
│ │ 5 documents • Last updated: 3 weeks ago  │ │
│ │ Academic records for Fall 2024           │ │
│ │ Current GPA: 3.8                         │ │
│ └─────────────────────────────────────────┘ │
│                                               │
└─────────────────────────────────────────────┘
```

**Components:**
- **Header**: Title + Create button
- **Search Bar**: Filter files by name/tags
- **Filter Dropdown**: Filter by document type (bill, finance, school, etc.)
- **File Cards**: Each shows:
  - Icon based on document type
  - Primary tag (bold) + secondary tags
  - Document count + last updated
  - 2-3 line summary preview
  - Chevron to navigate to detail

**Status Indicators:**
- 🟢 Generated (green dot)
- 🟡 Pending (yellow dot)
- 🔄 Regenerating (spinner)
- ⚠️ Outdated (orange dot)

---

### 2. File Detail Page (New)

**Route:** `/files/:fileId`

**Purpose:** View full file summary and list of documents

**Layout:**
```
┌─────────────────────────────────────────────┐
│ [← Back]  File Details          [⋯ Menu]    │
├─────────────────────────────────────────────┤
│                                               │
│ 📁 bill • lexus-tx-550                       │
│ 4 documents • Created Dec 2023               │
│                                               │
│ [🔄 Regenerate]        [+ Add Document]      │
│                                               │
│ ─────────────────────────────────────────── │
│                                               │
│ Summary                                       │
│ ─────────────────────────────────────────── │
│                                               │
│ Total maintenance costs for Lexus TX 550     │
│ in 2024: $934.50                             │
│                                               │
│ Average cost per service: $233.63            │
│ Most expensive: Brake service ($450)         │
│                                               │
│ Trend: Regular maintenance schedule being    │
│ followed with services every 3 months.       │
│ Next recommended service: Feb 2025           │
│                                               │
│ ─────────────────────────────────────────── │
│                                               │
│ Documents (4)                                 │
│ ─────────────────────────────────────────── │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📄 Nov 15, 2024 - Oil change        [>] │ │
│ │ $89.50 • Lexus dealer                    │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📄 Aug 10, 2024 - Tire rotation     [>] │ │
│ │ $45.00 • Service center                  │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📄 May 20, 2024 - 20k mile service  [>] │ │
│ │ $350.00 • Lexus dealer                   │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ 📄 Jan 15, 2024 - Oil change        [>] │ │
│ │ $89.50 • Lexus dealer                    │ │
│ └─────────────────────────────────────────┘ │
│                                               │
└─────────────────────────────────────────────┘
```

**Sections:**
1. **File Header**:
   - Icon + tags
   - Document count + created date
   - Actions: Regenerate, Add Document

2. **Summary Section**:
   - Full AI-generated summary
   - Collapsible/expandable if long
   - Shows insights, statistics, recommendations

3. **Documents List**:
   - Chronological order (newest first or oldest first toggle)
   - Each document card shows:
     - Date
     - Brief description/title
     - Key metadata (amount, vendor)
     - Tap to navigate to document detail

**Actions:**
- **Regenerate**: Force regeneration of summary
- **Add Document**: Opens document picker to add more docs
- **Menu**: Edit tags, delete file, share

---

### 3. Create File Flow

**Triggered from:** Documents Page or Files Page

**Steps:**

**Step 1 - Select Documents**
```
┌─────────────────────────────────────────────┐
│ [× Cancel]  Create File           [Next >]  │
├─────────────────────────────────────────────┤
│                                               │
│ Select Documents                              │
│ Choose documents to include in this file     │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ ☐ Nov 15, 2024 - Oil change             │ │
│ │   bill • lexus-tx-550                    │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ ☑ Aug 10, 2024 - Tire rotation          │ │
│ │   bill • lexus-tx-550                    │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ ┌─────────────────────────────────────────┐ │
│ │ ☑ May 20, 2024 - 20k service            │ │
│ │   bill • lexus-tx-550                    │ │
│ └─────────────────────────────────────────┘ │
│                                               │
│ 3 selected                                    │
│                                               │
└─────────────────────────────────────────────┘
```

**Step 2 - Choose Tags**
```
┌─────────────────────────────────────────────┐
│ [< Back]  Create File              [Create] │
├─────────────────────────────────────────────┤
│                                               │
│ File Tags                                     │
│ Tags define what documents to include        │
│                                               │
│ Document Type: [bill      ▾]                 │
│                                               │
│ Tags (select or add):                         │
│                                               │
│ Common tags from selected documents:          │
│ ┌─────┐ ┌──────────┐ ┌────────┐             │
│ │ ✓ lexus-tx-550 │ │ oil-change│            │
│ └─────┘ └──────────┘ └────────┘             │
│                                               │
│ All available tags:                           │
│ ┌─────┐ ┌──────────┐ ┌────────┐             │
│ │ pge │ │ electricity│ │ utilities│          │
│ └─────┘ └──────────┘ └────────┘             │
│                                               │
│ [+ Add custom tag]                            │
│                                               │
│ Preview: bill:lexus-tx-550                    │
│                                               │
└─────────────────────────────────────────────┘
```

**Step 3 - Confirmation**
```
┌─────────────────────────────────────────────┐
│        File Created Successfully! ✓          │
├─────────────────────────────────────────────┤
│                                               │
│ Your file is being generated...              │
│                                               │
│ [View File]    [Create Another]   [Done]     │
│                                               │
└─────────────────────────────────────────────┘
```

---

### 4. Integration with Documents Page

**Add "Create File" action to Documents Page:**

```
Documents Page Header:
┌─────────────────────────────────────────────┐
│ Documents                    [⋯] [+ Upload]  │
│                                               │
│ ... document list ...                         │
└─────────────────────────────────────────────┘

Long-press/Context menu on document:
┌─────────────────────────────────────────────┐
│ View Details                                  │
│ Add to File                                   │
│ Create File from This                         │
│ Delete                                        │
└─────────────────────────────────────────────┘
```

---

## Component Structure

```
web-ui/src/pages/
├── FilesPage.jsx            # List all files
├── FileDetailPage.jsx       # View single file with summary
└── CreateFilePage.jsx       # Create file flow

web-ui/src/components/
├── FileCard.jsx             # File list item
├── FileSummary.jsx          # Summary display component
├── DocumentPicker.jsx       # Multi-select document list
└── TagPicker.jsx            # Tag selection component
```

---

## API Integration

**Files Page:**
- `GET /api/v1/files` - List all files
- Poll for status changes (pending → generated)

**File Detail Page:**
- `GET /api/v1/files/{fileId}` - Get file with documents
- `POST /api/v1/files/{fileId}/regenerate` - Force regeneration
- `POST /api/v1/files/{fileId}/documents/{docId}` - Add document

**Create File Flow:**
- `POST /api/v1/files/create?document_type=bill&tags=lexus&document_ids=...`

---

## State Management

```javascript
// FilesPage state
{
  files: [],          // List of file objects
  loading: false,     // Loading state
  filter: 'all',      // Filter by type
  searchQuery: ''     // Search text
}

// FileDetailPage state
{
  file: {},           // File object with summary
  documents: [],      // List of documents in file
  loading: false,
  regenerating: false // Regeneration in progress
}

// CreateFilePage state
{
  step: 1,            // Current step (1-3)
  selectedDocs: [],   // Selected document IDs
  documentType: '',   // Chosen document type
  selectedTags: [],   // Chosen tags
  creating: false     // Creation in progress
}
```

---

## Visual Design Notes

**Colors:**
- File cards: Light background with subtle border
- Status indicators: Semantic colors (green/yellow/orange)
- Summary section: White/light gray background
- Document list items: Slightly darker than file cards

**Typography:**
- File tags: Bold, larger font
- Summary text: Regular weight, comfortable line height
- Document dates: Smaller, gray text
- Amounts: Bold, highlighted

**Icons:**
- 📁 Files (general)
- 💰 Bills/Finance
- 🎓 School/Education
- 🎟️ Events
- 🗑️ Junk

---

## Mobile Considerations

- **Swipe Actions**: Swipe file card left for quick actions (regenerate, delete)
- **Pull to Refresh**: On Files Page
- **Long Press**: Context menu for files and documents
- **Bottom Sheets**: For filters and tag selection (better than dropdowns on mobile)
- **Loading States**: Show skeleton screens while generating summaries
- **Empty States**: Friendly messages when no files exist

---

## Implementation Priority

1. **Phase 1** (MVP):
   - Files Page with list
   - File Detail Page with summary
   - Basic create file flow

2. **Phase 2** (Polish):
   - Search and filters
   - Swipe actions
   - Status polling
   - Empty states

3. **Phase 3** (Advanced):
   - Tag suggestions
   - Auto-file creation suggestions
   - File templates
   - Export/share functionality

---

## Example User Journey

**Scenario:** User wants to track all their Lexus maintenance bills

1. User navigates to Documents Page
2. Filters documents by type "bill" and manually adds tag "lexus-tx-550" to 4 documents
3. Clicks "Create File" button
4. Selects the 4 Lexus documents
5. System suggests tags: "lexus-tx-550" (common tag)
6. User confirms and creates file
7. System queues file for generation (status: pending)
8. User sees "File created successfully!" notification
9. User navigates to Files Page
10. Sees new file with status "Generating..." (spinner)
11. After ~10-15 seconds, status changes to "Generated"
12. User taps file to view detail page
13. Sees AI summary: "Total maintenance costs for Lexus TX 550 in 2024: $934.50..."
14. User reviews chronological list of documents
15. User adds new oil change document next month
16. File automatically marked "outdated" and regenerates with updated summary

---

**Status:** Ready for implementation
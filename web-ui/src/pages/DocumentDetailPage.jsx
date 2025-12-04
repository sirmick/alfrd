import { useState, useEffect } from 'react'
import { 
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonBadge,
  IonSpinner,
  IonButtons,
  IonBackButton,
  IonItem,
  IonLabel,
  IonList,
  IonListHeader,
  IonThumbnail,
  IonButton,
  IonIcon
} from '@ionic/react'
import { useParams } from 'react-router-dom'
import { openOutline } from 'ionicons/icons'

function DocumentDetailPage() {
  const { id } = useParams()
  const [document, setDocument] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchDocument()
  }, [id])

  const fetchDocument = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`/api/v1/documents/${id}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch document: ${response.statusText}`)
      }
      
      const data = await response.json()
      
      // Ensure tags is an array (API now returns proper types)
      if (!data.tags || !Array.isArray(data.tags)) {
        data.tags = []
      }
      
      // Ensure structured_data is an object (API now returns proper types)
      if (!data.structured_data || typeof data.structured_data !== 'object') {
        data.structured_data = {}
      }
      
      setDocument(data)
    } catch (err) {
      console.error('Error fetching document:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status) => {
    const colors = {
      'completed': 'success',
      'pending': 'warning',
      'ocr_completed': 'primary',
      'classified': 'secondary',
      'error': 'danger'
    }
    return colors[status] || 'medium'
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleString()
  }

  if (loading) {
    return (
      <IonPage>
        <IonHeader>
          <IonToolbar>
            <IonButtons slot="start">
              <IonBackButton defaultHref="/documents" />
            </IonButtons>
            <IonTitle>Loading...</IonTitle>
          </IonToolbar>
        </IonHeader>
        <IonContent>
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading document...</p>
          </div>
        </IonContent>
      </IonPage>
    )
  }

  if (error || !document) {
    return (
      <IonPage>
        <IonHeader>
          <IonToolbar>
            <IonButtons slot="start">
              <IonBackButton defaultHref="/documents" />
            </IonButtons>
            <IonTitle>Error</IonTitle>
          </IonToolbar>
        </IonHeader>
        <IonContent>
          <IonCard color="danger">
            <IonCardHeader>
              <IonCardTitle>Error Loading Document</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>{error || 'Document not found'}</IonCardContent>
          </IonCard>
        </IonContent>
      </IonPage>
    )
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/documents" />
          </IonButtons>
          <IonTitle>{document.document_type || 'Document'}</IonTitle>
        </IonToolbar>
      </IonHeader>
      
      <IonContent className="ion-padding">
        {/* Image Preview - Show first if available */}
        {document.files && document.files.length > 0 && document.files[0].filename.match(/\.(jpg|jpeg|png|webp)$/i) && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Preview</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <img
                src={document.files[0].url}
                alt="Document preview"
                style={{ width: '100%', maxHeight: '400px', objectFit: 'contain' }}
              />
            </IonCardContent>
          </IonCard>
        )}

        {/* Status and Type */}
        <IonCard>
          <IonCardHeader>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <IonCardTitle>Document Info</IonCardTitle>
              <IonBadge color={getStatusColor(document.status)}>
                {document.status}
              </IonBadge>
            </div>
          </IonCardHeader>
          <IonCardContent>
            <IonList>
              <IonItem>
                <IonLabel>
                  <h3>Type</h3>
                  <p>{document.document_type || 'Unknown'}</p>
                </IonLabel>
              </IonItem>
              
              {document.suggested_type && (
                <IonItem>
                  <IonLabel>
                    <h3>Suggested Type</h3>
                    <p>{document.suggested_type}</p>
                  </IonLabel>
                </IonItem>
              )}
              
              <IonItem>
                <IonLabel>
                  <h3>Created</h3>
                  <p>{formatDate(document.created_at)}</p>
                </IonLabel>
              </IonItem>
              
              {document.updated_at && (
                <IonItem>
                  <IonLabel>
                    <h3>Last Updated</h3>
                    <p>{formatDate(document.updated_at)}</p>
                  </IonLabel>
                </IonItem>
              )}
            </IonList>
          </IonCardContent>
        </IonCard>

        {/* Summary */}
        {document.summary && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Summary</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <p style={{ fontSize: '1.1em', fontStyle: 'italic' }}>{document.summary}</p>
            </IonCardContent>
          </IonCard>
        )}

        {/* Structured Data (extracted fields from summarization) */}
        {document.structured_data && Object.keys(document.structured_data).length > 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Extracted Information</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              {/* Show raw JSON first for debugging */}
              <details style={{ marginBottom: '16px' }}>
                <summary style={{ cursor: 'pointer', fontWeight: 'bold', color: 'var(--ion-color-primary)' }}>
                  View Raw JSON
                </summary>
                <pre style={{
                  whiteSpace: 'pre-wrap',
                  fontSize: '0.85em',
                  backgroundColor: '#f5f5f5',
                  padding: '10px',
                  borderRadius: '4px',
                  overflow: 'auto'
                }}>
                  {JSON.stringify(document.structured_data, null, 2)}
                </pre>
              </details>
              
              {/* Display formatted fields */}
              <IonList>
                {Object.entries(document.structured_data)
                  .filter(([key]) => key !== 'summary')  // Skip summary since we show it separately
                  .map(([key, value]) => (
                  <IonItem key={key}>
                    <IonLabel>
                      <h3>{key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h3>
                      <p style={{ whiteSpace: 'pre-wrap', fontSize: '0.9em' }}>
                        {typeof value === 'object' && value !== null
                          ? JSON.stringify(value, null, 2)
                          : String(value)
                        }
                      </p>
                    </IonLabel>
                  </IonItem>
                ))}
              </IonList>
            </IonCardContent>
          </IonCard>
        )}

        {/* Tags */}
        {document.tags && document.tags.length > 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Tags</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {document.tags.map((tag, idx) => (
                  <IonBadge key={idx} color="primary" style={{ marginBottom: '8px' }}>
                    {tag}
                  </IonBadge>
                ))}
              </div>
            </IonCardContent>
          </IonCard>
        )}

        {/* OCR Info */}
        {(document.confidence || document.ocr_confidence) && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>OCR Details</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <IonList>
                <IonItem>
                  <IonLabel>
                    <h3>OCR Confidence</h3>
                    <p>{Math.round((document.confidence || document.ocr_confidence) * 100)}%</p>
                  </IonLabel>
                </IonItem>
                {document.classification_confidence && (
                  <IonItem>
                    <IonLabel>
                      <h3>Classification Confidence</h3>
                      <p>{Math.round(document.classification_confidence * 100)}%</p>
                    </IonLabel>
                  </IonItem>
                )}
              </IonList>
              
              {document.extracted_text && (
                <div style={{ marginTop: '16px' }}>
                  <h3>Extracted Text (OCR)</h3>
                  <pre style={{ 
                    whiteSpace: 'pre-wrap', 
                    fontSize: '0.85em', 
                    backgroundColor: '#f5f5f5', 
                    padding: '10px',
                    borderRadius: '4px',
                    maxHeight: '200px',
                    overflow: 'auto'
                  }}>
                    {document.extracted_text}
                  </pre>
                </div>
              )}
            </IonCardContent>
          </IonCard>
        )}

        {/* Original Files */}
        {document.files && document.files.length > 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>Original Files</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <IonList>
                {document.files.map((file, idx) => (
                  <IonItem key={idx} button href={file.url} target="_blank">
                    <IonLabel>{file.filename}</IonLabel>
                    <IonIcon icon={openOutline} slot="end" />
                  </IonItem>
                ))}
              </IonList>
            </IonCardContent>
          </IonCard>
        )}

        {/* Error Message */}
        {document.error_message && (
          <IonCard color="danger">
            <IonCardHeader>
              <IonCardTitle>Error</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.85em' }}>
                {document.error_message}
              </pre>
            </IonCardContent>
          </IonCard>
        )}
      </IonContent>
    </IonPage>
  )
}

export default DocumentDetailPage
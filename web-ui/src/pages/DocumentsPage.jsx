import { useState, useEffect } from 'react'
import { 
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonButton,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonIcon,
  IonBadge,
  IonSpinner,
  IonRefresher,
  IonRefresherContent,
  IonFab,
  IonFabButton,
  IonLabel,
  IonItem,
  IonList
} from '@ionic/react'
import { camera, documentText, refresh } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'

function DocumentsPage() {
  const history = useHistory()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchDocuments = async () => {
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch('/api/v1/documents?limit=50')
      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.statusText}`)
      }
      
      const data = await response.json()
      setDocuments(data.documents || [])
    } catch (err) {
      console.error('Error fetching documents:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDocuments()
  }, [])

  const handleRefresh = async (event) => {
    await fetchDocuments()
    event?.detail?.complete()
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
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonTitle>ALFRD Documents</IonTitle>
          <IonButton slot="end" fill="clear" onClick={fetchDocuments}>
            <IonIcon icon={refresh} />
          </IonButton>
        </IonToolbar>
      </IonHeader>
      
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent></IonRefresherContent>
        </IonRefresher>

        {loading && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading documents...</p>
          </div>
        )}

        {error && (
          <IonCard color="danger">
            <IonCardHeader>
              <IonCardTitle>Error</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>{error}</IonCardContent>
          </IonCard>
        )}

        {!loading && !error && documents.length === 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>No Documents</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <p>No documents found. Upload your first document by tapping the camera button below.</p>
            </IonCardContent>
          </IonCard>
        )}

        {!loading && !error && documents.length > 0 && (
          <IonList>
            {documents.map((doc) => (
              <IonCard 
                key={doc.id} 
                button 
                onClick={() => history.push(`/documents/${doc.id}`)}
                style={{ margin: '10px' }}
              >
                <IonCardHeader>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <IonCardTitle>
                      <IonIcon icon={documentText} style={{ marginRight: '8px' }} />
                      {doc.document_type || 'Unknown Type'}
                    </IonCardTitle>
                    <IonBadge color={getStatusColor(doc.status)}>
                      {doc.status}
                    </IonBadge>
                  </div>
                </IonCardHeader>
                <IonCardContent>
                  <p style={{ fontSize: '0.9em', color: '#666', marginBottom: '8px' }}>
                    {formatDate(doc.created_at)}
                  </p>
                  
                  {doc.summary && (
                    <p style={{
                      marginTop: '8px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical',
                      fontStyle: 'italic'
                    }}>
                      {doc.summary}
                    </p>
                  )}
                  
                  {doc.secondary_tags && doc.secondary_tags.length > 0 && (
                    <div style={{ marginTop: '8px' }}>
                      {doc.secondary_tags.map((tag, idx) => (
                        <IonBadge key={idx} color="light" style={{ marginRight: '4px' }}>
                          {tag}
                        </IonBadge>
                      ))}
                    </div>
                  )}
                  
                  {doc.classification_confidence && (
                    <p style={{ fontSize: '0.85em', color: '#999', marginTop: '8px' }}>
                      Confidence: {Math.round(doc.classification_confidence * 100)}%
                    </p>
                  )}
                </IonCardContent>
              </IonCard>
            ))}
          </IonList>
        )}

        <IonFab vertical="bottom" horizontal="end" slot="fixed">
          <IonFabButton onClick={() => history.push('/capture')}>
            <IonIcon icon={camera} />
          </IonFabButton>
        </IonFab>
      </IonContent>
    </IonPage>
  )
}

export default DocumentsPage
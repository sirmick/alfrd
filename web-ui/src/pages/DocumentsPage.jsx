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
  IonList,
  IonSearchbar
} from '@ionic/react'
import { camera, documentText, refresh, close } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'

function DocumentsPage() {
  const history = useHistory()
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)

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

  const performSearch = async (query) => {
    if (!query || query.trim().length === 0) {
      // If search is cleared, reload all documents
      setIsSearching(false)
      await fetchDocuments()
      return
    }

    try {
      setLoading(true)
      setError(null)
      setIsSearching(true)
      
      const response = await fetch(`/api/v1/documents/search?q=${encodeURIComponent(query)}&limit=50`)
      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`)
      }
      
      const data = await response.json()
      setDocuments(data.results || [])
    } catch (err) {
      console.error('Error searching documents:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSearchChange = (e) => {
    const query = e.detail.value
    setSearchQuery(query)
    
    // Debounce search - only search after user stops typing for 500ms
    const timeoutId = setTimeout(() => {
      performSearch(query)
    }, 500)
    
    return () => clearTimeout(timeoutId)
  }

  const clearSearch = () => {
    setSearchQuery('')
    setIsSearching(false)
    fetchDocuments()
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
        <IonToolbar>
          <IonSearchbar
            value={searchQuery}
            onIonInput={handleSearchChange}
            placeholder="Search documents..."
            debounce={500}
            showClearButton="always"
          />
          {isSearching && (
            <IonButton slot="end" fill="clear" onClick={clearSearch}>
              <IonIcon icon={close} />
              Clear Search
            </IonButton>
          )}
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
              <IonCardTitle>{isSearching ? 'No Results' : 'No Documents'}</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              {isSearching ? (
                <p>No documents match your search query. Try different keywords.</p>
              ) : (
                <p>No documents found. Upload your first document by tapping the camera button below.</p>
              )}
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
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      {/* Main line: Summary and date */}
                      <IonCardTitle style={{ fontSize: '1.1em', marginBottom: '4px' }}>
                        {doc.summary || doc.document_type || 'Untitled Document'}
                      </IonCardTitle>
                      <p style={{ fontSize: '0.85em', color: '#666', margin: '0 0 8px 0' }}>
                        {formatDate(doc.created_at)}
                      </p>
                    </div>
                    <IonBadge color={getStatusColor(doc.status)}>
                      {doc.status}
                    </IonBadge>
                  </div>
                </IonCardHeader>
                <IonCardContent>
                  {/* Second line: Type and tags */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                    {/* Document type badge */}
                    {doc.document_type && (
                      <IonBadge color="primary" style={{ marginRight: '4px' }}>
                        {doc.document_type}
                      </IonBadge>
                    )}
                    
                    {/* Secondary tags */}
                    {doc.secondary_tags && doc.secondary_tags.length > 0 && (
                      doc.secondary_tags.map((tag, idx) => (
                        <IonBadge key={idx} color="secondary" style={{ marginRight: '4px' }}>
                          {tag}
                        </IonBadge>
                      ))
                    )}
                    
                    {/* Classification confidence */}
                    {doc.classification_confidence && (
                      <IonBadge color="light" style={{ marginLeft: 'auto' }}>
                        {Math.round(doc.classification_confidence * 100)}%
                      </IonBadge>
                    )}
                  </div>
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
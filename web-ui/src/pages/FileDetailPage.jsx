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
  IonList,
  IonBackButton,
  IonButtons,
  IonActionSheet,
  IonToast
} from '@ionic/react'
import { 
  arrowBack, 
  ellipsisVertical, 
  reload, 
  add, 
  documentText,
  chevronForward 
} from 'ionicons/icons'
import { useHistory, useParams } from 'react-router-dom'

function FileDetailPage() {
  const history = useHistory()
  const { id: fileId } = useParams()
  
  console.log('[FileDetailPage] Component mounted with fileId:', fileId)
  console.log('[FileDetailPage] fileId type:', typeof fileId)
  console.log('[FileDetailPage] isNaN check:', isNaN(parseInt(fileId)))
  console.log('[FileDetailPage] Current pathname:', window.location.pathname)
  
  const [file, setFile] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showActionSheet, setShowActionSheet] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [toast, setToast] = useState({ show: false, message: '' })

  const fetchFileDetails = async () => {
    console.log('[fetchFileDetails] Called with fileId:', fileId)
    try {
      setLoading(true)
      setError(null)
      
      const response = await fetch(`/api/v1/files/${fileId}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch file: ${response.statusText}`)
      }
      
      const data = await response.json()
      setFile(data.file || {})
      setDocuments(data.documents || [])
    } catch (err) {
      console.error('Error fetching file:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    console.log('[useEffect] Running with fileId:', fileId)
    
    // Skip if fileId is not a valid number (e.g., "create")
    if (!fileId || isNaN(parseInt(fileId))) {
      console.log('[useEffect] SKIPPING - Invalid fileId detected:', fileId)
      setError('Invalid file ID')
      setLoading(false)
      return
    }
    
    console.log('[useEffect] Valid fileId, calling fetchFileDetails')
    fetchFileDetails()
    
    // Poll for status changes every 3 seconds
    const interval = setInterval(fetchFileDetails, 3000)
    return () => clearInterval(interval)
  }, [fileId])

  const handleRefresh = async (event) => {
    await fetchFileDetails()
    event?.detail?.complete()
  }

  const handleRegenerate = async () => {
    try {
      setRegenerating(true)
      const response = await fetch(`/api/v1/files/${fileId}/regenerate`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        throw new Error('Failed to regenerate file')
      }
      
      setToast({ show: true, message: 'File queued for regeneration' })
      await fetchFileDetails()
    } catch (err) {
      console.error('Error regenerating file:', err)
      setToast({ show: true, message: `Error: ${err.message}` })
    } finally {
      setRegenerating(false)
    }
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const getStatusColor = (status) => {
    const colors = {
      'generated': 'success',
      'pending': 'warning',
      'outdated': 'warning',
      'regenerating': 'primary'
    }
    return colors[status] || 'medium'
  }

  const renderSummary = () => {
    if (!file) return null

    if (file.status === 'pending') {
      return (
        <IonCard>
          <IonCardContent>
            <div style={{ textAlign: 'center', padding: '20px' }}>
              <IonSpinner name="crescent" />
              <p style={{ marginTop: '10px', color: '#666' }}>
                Generating summary...
              </p>
            </div>
          </IonCardContent>
        </IonCard>
      )
    }

    if (file.status === 'regenerating') {
      return (
        <IonCard>
          <IonCardContent>
            <div style={{ textAlign: 'center', padding: '20px' }}>
              <IonSpinner name="crescent" />
              <p style={{ marginTop: '10px', color: '#666' }}>
                Regenerating summary...
              </p>
            </div>
          </IonCardContent>
        </IonCard>
      )
    }

    if (file.status === 'generated' && file.summary_text) {
      return (
        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Summary</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
              {file.summary_text}
            </div>
            
            {file.summary_metadata && Object.keys(file.summary_metadata).length > 0 && (
              <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid #ddd' }}>
                {file.summary_metadata.insights && file.summary_metadata.insights.length > 0 && (
                  <div style={{ marginBottom: '15px' }}>
                    <strong>Key Insights:</strong>
                    <ul style={{ marginTop: '8px' }}>
                      {file.summary_metadata.insights.map((insight, idx) => (
                        <li key={idx}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {file.summary_metadata.statistics && Object.keys(file.summary_metadata.statistics).length > 0 && (
                  <div style={{ marginBottom: '15px' }}>
                    <strong>Statistics:</strong>
                    <ul style={{ marginTop: '8px' }}>
                      {Object.entries(file.summary_metadata.statistics).map(([key, value]) => (
                        <li key={key}>{key}: {value}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {file.summary_metadata.recommendations && file.summary_metadata.recommendations.length > 0 && (
                  <div>
                    <strong>Recommendations:</strong>
                    <ul style={{ marginTop: '8px' }}>
                      {file.summary_metadata.recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </IonCardContent>
        </IonCard>
      )
    }

    return null
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/files" />
          </IonButtons>
          <IonTitle>File Details</IonTitle>
          <IonButton slot="end" fill="clear" onClick={() => setShowActionSheet(true)}>
            <IonIcon icon={ellipsisVertical} />
          </IonButton>
        </IonToolbar>
      </IonHeader>
      
      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent></IonRefresherContent>
        </IonRefresher>

        {loading && !file && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading file...</p>
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

        {file && (
          <>
            {/* File Header */}
            <IonCard>
              <IonCardHeader>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap', marginBottom: '8px' }}>
                      <IonBadge color="primary">{file.document_type}</IonBadge>
                      {Array.isArray(file.tags) && file.tags.map((tag, idx) => (
                        <IonBadge key={idx} color="secondary">{tag}</IonBadge>
                      ))}
                    </div>
                    <div style={{ fontSize: '0.85em', color: '#666' }}>
                      {file.document_count || 0} document{file.document_count !== 1 ? 's' : ''} • 
                      Created {formatDate(file.created_at)}
                    </div>
                  </div>
                  <IonBadge color={getStatusColor(file.status)}>
                    {file.status}
                  </IonBadge>
                </div>
              </IonCardHeader>
              <IonCardContent>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <IonButton 
                    expand="block" 
                    fill="outline" 
                    onClick={handleRegenerate}
                    disabled={regenerating || file.status === 'regenerating'}
                    style={{ flex: 1 }}
                  >
                    <IonIcon icon={reload} slot="start" />
                    {regenerating ? 'Regenerating...' : 'Regenerate'}
                  </IonButton>
                  <IonButton 
                    expand="block" 
                    fill="outline"
                    onClick={() => history.push(`/files/${fileId}/add-document`)}
                    style={{ flex: 1 }}
                  >
                    <IonIcon icon={add} slot="start" />
                    Add Document
                  </IonButton>
                </div>
              </IonCardContent>
            </IonCard>

            {/* Summary Section */}
            {renderSummary()}

            {/* Documents List */}
            {documents.length > 0 && (
              <IonCard>
                <IonCardHeader>
                  <IonCardTitle>
                    Documents ({documents.length})
                  </IonCardTitle>
                </IonCardHeader>
                <IonList>
                  {documents.map((doc) => (
                    <IonCard
                      key={doc.id}
                      button
                      onClick={() => history.push(`/documents/${doc.id}`)}
                      style={{ margin: '8px' }}
                    >
                      <IonCardHeader>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: '0.85em', color: '#666', marginBottom: '4px' }}>
                              {formatDate(doc.created_at)}
                            </div>
                            <div style={{ fontSize: '1em', fontWeight: '500' }}>
                              {doc.summary || doc.filename || 'Untitled'}
                            </div>
                          </div>
                          <IonIcon icon={chevronForward} style={{ color: '#999' }} />
                        </div>
                      </IonCardHeader>
                      {doc.structured_data && Object.keys(doc.structured_data).length > 0 && (
                        <IonCardContent>
                          <div style={{ fontSize: '0.85em', color: '#666' }}>
                            {Object.entries(doc.structured_data).slice(0, 2).map(([key, value]) => (
                              <div key={key}>{key}: {value}</div>
                            ))}
                          </div>
                        </IonCardContent>
                      )}
                    </IonCard>
                  ))}
                </IonList>
              </IonCard>
            )}
          </>
        )}

        <IonActionSheet
          isOpen={showActionSheet}
          onDidDismiss={() => setShowActionSheet(false)}
          buttons={[
            {
              text: 'Regenerate Summary',
              icon: reload,
              handler: () => {
                handleRegenerate()
              }
            },
            {
              text: 'Add Document',
              icon: add,
              handler: () => {
                history.push(`/files/${fileId}/add-document`)
              }
            },
            {
              text: 'Cancel',
              role: 'cancel'
            }
          ]}
        />

        <IonToast
          isOpen={toast.show}
          onDidDismiss={() => setToast({ show: false, message: '' })}
          message={toast.message}
          duration={2000}
        />
      </IonContent>
    </IonPage>
  )
}

export default FileDetailPage
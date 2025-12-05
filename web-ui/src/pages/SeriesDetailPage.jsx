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
  IonBackButton,
  IonButtons,
  IonList,
  IonItem,
  IonLabel,
  IonRefresher,
  IonRefresherContent,
  IonAlert
} from '@ionic/react'
import { refresh, documentText, sparkles } from 'ionicons/icons'
import { useParams, useHistory } from 'react-router-dom'

function SeriesDetailPage() {
  const { id } = useParams()
  const history = useHistory()
  const [series, setSeries] = useState(null)
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [regenerating, setRegenerating] = useState(false)
  const [showRegenerateAlert, setShowRegenerateAlert] = useState(false)

  const fetchSeriesDetails = async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Fetch series metadata
      const seriesResponse = await fetch(`/api/v1/series/${id}`)
      if (!seriesResponse.ok) {
        throw new Error(`Failed to fetch series: ${seriesResponse.statusText}`)
      }
      const seriesData = await seriesResponse.json()
      setSeries(seriesData)
      
      // Documents are included in the series response
      setDocuments(seriesData.documents || [])
    } catch (err) {
      console.error('Error fetching series details:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async () => {
    try {
      setRegenerating(true)
      setShowRegenerateAlert(false)
      
      const response = await fetch(`/api/v1/series/${id}/regenerate`, {
        method: 'POST'
      })
      
      if (!response.ok) {
        throw new Error(`Regeneration failed: ${response.statusText}`)
      }
      
      // Refresh the series data
      await fetchSeriesDetails()
    } catch (err) {
      console.error('Error regenerating series:', err)
      setError(err.message)
    } finally {
      setRegenerating(false)
    }
  }

  useEffect(() => {
    fetchSeriesDetails()
  }, [id])

  const handleRefresh = async (event) => {
    await fetchSeriesDetails()
    event?.detail?.complete()
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const formatShortDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString()
  }

  const getStatusColor = (status) => {
    const colors = {
      'active': 'success',
      'completed': 'medium',
      'archived': 'light'
    }
    return colors[status] || 'medium'
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/series" />
          </IonButtons>
          <IonTitle>Series Details</IonTitle>
          <IonButton slot="end" fill="clear" onClick={fetchSeriesDetails} disabled={loading}>
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
            <p>Loading series details...</p>
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

        {!loading && !error && series && (
          <>
            {/* Series Information Card */}
            <IonCard>
              <IonCardHeader>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <IonCardTitle>{series.title}</IonCardTitle>
                    <p style={{ fontSize: '0.9em', color: '#666', margin: '4px 0 0 0' }}>
                      {series.entity}
                    </p>
                  </div>
                  <IonBadge color={getStatusColor(series.status)}>
                    {series.status}
                  </IonBadge>
                </div>
              </IonCardHeader>
              <IonCardContent>
                {/* Description */}
                {series.description && (
                  <p style={{ marginBottom: '12px', color: '#333' }}>
                    {series.description}
                  </p>
                )}
                
                {/* Metadata badges */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
                  <IonBadge color="primary">
                    {series.series_type?.replace(/_/g, ' ')}
                  </IonBadge>
                  
                  {series.frequency && (
                    <IonBadge color="secondary">
                      {series.frequency}
                    </IonBadge>
                  )}
                  
                  <IonBadge color="light">
                    {series.document_count || 0} documents
                  </IonBadge>
                  
                  {series.source && (
                    <IonBadge color="tertiary">
                      {series.source}
                    </IonBadge>
                  )}
                </div>
                
                {/* Date range */}
                {series.first_document_date && series.last_document_date && (
                  <IonItem lines="none">
                    <IonLabel>
                      <h3>Date Range</h3>
                      <p>{formatShortDate(series.first_document_date)} - {formatShortDate(series.last_document_date)}</p>
                    </IonLabel>
                  </IonItem>
                )}
                
                {/* Metadata (if any) */}
                {series.metadata && Object.keys(series.metadata).length > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    <h4 style={{ fontSize: '0.9em', margin: '0 0 8px 0', color: '#666' }}>Additional Information</h4>
                    <div style={{ background: '#f4f4f4', padding: '8px', borderRadius: '4px' }}>
                      {Object.entries(series.metadata).map(([key, value]) => (
                        <div key={key} style={{ fontSize: '0.85em', marginBottom: '4px' }}>
                          <strong>{key}:</strong> {String(value)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Regenerate button */}
                <IonButton
                  expand="block"
                  onClick={() => setShowRegenerateAlert(true)}
                  disabled={regenerating}
                  style={{ marginTop: '16px' }}
                >
                  <IonIcon icon={sparkles} slot="start" />
                  {regenerating ? 'Regenerating...' : 'Regenerate Summary'}
                </IonButton>
              </IonCardContent>
            </IonCard>

            {/* Summary Card (if available) */}
            {series.summary_text && (
              <IonCard>
                <IonCardHeader>
                  <IonCardTitle>Summary</IonCardTitle>
                </IonCardHeader>
                <IonCardContent>
                  <p style={{ whiteSpace: 'pre-wrap' }}>{series.summary_text}</p>
                  
                  {series.last_generated_at && (
                    <p style={{ fontSize: '0.75em', color: '#999', marginTop: '12px' }}>
                      Last generated: {formatDate(series.last_generated_at)}
                    </p>
                  )}
                </IonCardContent>
              </IonCard>
            )}

            {/* Documents List */}
            <IonCard>
              <IonCardHeader>
                <IonCardTitle>Documents ({documents.length})</IonCardTitle>
              </IonCardHeader>
              <IonCardContent style={{ padding: 0 }}>
                {documents.length === 0 ? (
                  <p style={{ padding: '16px', textAlign: 'center', color: '#666' }}>
                    No documents in this series yet.
                  </p>
                ) : (
                  <IonList>
                    {documents.map((doc) => (
                      <IonItem
                        key={doc.id}
                        button
                        onClick={() => history.push(`/documents/${doc.id}`)}
                      >
                        <IonIcon icon={documentText} slot="start" />
                        <IonLabel>
                          <h3>{doc.summary || doc.filename || 'Untitled'}</h3>
                          <p>{formatDate(doc.created_at)}</p>
                        </IonLabel>
                        {doc.document_type && (
                          <IonBadge color="primary" slot="end">
                            {doc.document_type}
                          </IonBadge>
                        )}
                      </IonItem>
                    ))}
                  </IonList>
                )}
              </IonCardContent>
            </IonCard>
          </>
        )}

        {/* Regenerate Confirmation Alert */}
        <IonAlert
          isOpen={showRegenerateAlert}
          onDidDismiss={() => setShowRegenerateAlert(false)}
          header="Regenerate Summary"
          message="This will regenerate the series summary using the latest documents and LLM prompt. Continue?"
          buttons={[
            {
              text: 'Cancel',
              role: 'cancel'
            },
            {
              text: 'Regenerate',
              handler: handleRegenerate
            }
          ]}
        />
      </IonContent>
    </IonPage>
  )
}

export default SeriesDetailPage
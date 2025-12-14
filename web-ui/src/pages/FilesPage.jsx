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
  IonFab,
  IonFabButton
} from '@ionic/react'
import { folder, add, refresh } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'

function FilesPage() {
  const history = useHistory()
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchFiles = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch('/api/v1/files?limit=50')
      if (!response.ok) {
        throw new Error(`Failed to fetch files: ${response.statusText}`)
      }

      const data = await response.json()
      setFiles(data.files || [])
    } catch (err) {
      console.error('Error fetching files:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchFiles()

    // Poll for status changes every 5 seconds
    const interval = setInterval(fetchFiles, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleRefresh = async (event) => {
    await fetchFiles()
    event?.detail?.complete()
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

  const getStatusIcon = (status) => {
    if (status === 'regenerating') return <IonSpinner name="crescent" style={{ width: '12px', height: '12px' }} />
    if (status === 'generated') return null
    if (status === 'outdated') return null
    if (status === 'pending') return null
    return null
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now - date
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays} days ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
    return date.toLocaleDateString()
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <div slot="start" style={{ display: 'flex', alignItems: 'center', marginLeft: '10px' }}>
            <img src="/ALFRD.svg" alt="ALFRD Logo" style={{ height: '32px', width: 'auto' }} />
          </div>
          <IonTitle>Files</IonTitle>
          <IonButton slot="end" fill="clear" onClick={fetchFiles}>
            <IonIcon icon={refresh} />
          </IonButton>
        </IonToolbar>
      </IonHeader>

      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent></IonRefresherContent>
        </IonRefresher>

        {loading && files.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading files...</p>
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

        {!loading && !error && files.length === 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>No Files</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <p>No files created yet. Files group related documents with AI-generated summaries.</p>
              <p style={{ marginTop: '10px' }}>Create your first file by clicking the + button below.</p>
            </IonCardContent>
          </IonCard>
        )}

        {files.length > 0 && (
          <IonList>
            {files.map((file) => (
              <IonCard
                key={file.id}
                button
                onClick={() => history.push(`/files/${file.id}`)}
                style={{ margin: '10px' }}
              >
                <IonCardHeader>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <IonIcon icon={folder} style={{ fontSize: '24px', color: '#3880ff' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexWrap: 'wrap' }}>
                        {Array.isArray(file.tags) && file.tags.length > 0 ? (
                          file.tags.map((tag, idx) => (
                            <IonBadge key={idx} color={idx === 0 ? "primary" : "secondary"}>{tag}</IonBadge>
                          ))
                        ) : (
                          <IonBadge color="medium">No tags</IonBadge>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {getStatusIcon(file.status)}
                      <IonBadge color={getStatusColor(file.status)}>
                        {file.status}
                      </IonBadge>
                    </div>
                  </div>

                  <div style={{ fontSize: '0.85em', color: '#666', marginTop: '4px' }}>
                    {file.document_count ?? 0} document{(file.document_count ?? 0) !== 1 ? 's' : ''} •
                    Last updated: {formatDate(file.updated_at)}
                  </div>
                </IonCardHeader>

                {file.summary_text && file.status === 'generated' && (
                  <IonCardContent>
                    <p style={{
                      margin: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 3,
                      WebkitBoxOrient: 'vertical',
                      color: '#555'
                    }}>
                      {file.summary_text}
                    </p>
                  </IonCardContent>
                )}

                {file.status === 'pending' && (
                  <IonCardContent>
                    <p style={{ margin: 0, color: '#666', fontStyle: 'italic' }}>
                      Summary generation queued...
                    </p>
                  </IonCardContent>
                )}

                {file.status === 'regenerating' && (
                  <IonCardContent>
                    <p style={{ margin: 0, color: '#666', fontStyle: 'italic' }}>
                      Regenerating summary...
                    </p>
                  </IonCardContent>
                )}
              </IonCard>
            ))}
          </IonList>
        )}

        <IonFab vertical="bottom" horizontal="end" slot="fixed">
          <IonFabButton onClick={() => history.push('/files/create')}>
            <IonIcon icon={add} />
          </IonFabButton>
        </IonFab>
      </IonContent>
    </IonPage>
  )
}

export default FilesPage

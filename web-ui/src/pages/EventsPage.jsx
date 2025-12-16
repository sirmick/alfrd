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
  IonBackButton,
  IonButtons,
  IonButton,
  IonIcon,
  IonRefresher,
  IonRefresherContent,
  IonSegment,
  IonSegmentButton,
  IonLabel,
  IonList,
  IonItem
} from '@ionic/react'
import { useLocation, useHistory } from 'react-router-dom'
import {
  refresh,
  alertCircle,
  checkmarkCircle,
  sync,
  chatbubble,
  warning,
  person,
  time,
  arrowForward
} from 'ionicons/icons'
import { useAuth } from '../context/AuthContext'

function EventsPage() {
  const location = useLocation()
  const history = useHistory()
  const { authFetch } = useAuth()
  const searchParams = new URLSearchParams(location.search)

  // Get entity ID and type from query params
  const documentId = searchParams.get('document_id')
  const fileId = searchParams.get('file_id')
  const seriesId = searchParams.get('series_id')
  const entityId = searchParams.get('id') || documentId || fileId || seriesId

  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [entityInfo, setEntityInfo] = useState(null)

  // Determine back URL based on entity type
  const getBackUrl = () => {
    if (documentId) return `/documents/${documentId}`
    if (fileId) return `/files/${fileId}`
    if (seriesId) return `/series/${seriesId}`
    return '/documents'
  }

  // Get page title based on entity
  const getPageTitle = () => {
    if (entityInfo) {
      if (documentId) return `Events: ${entityInfo.document_type || 'Document'}`
      if (fileId) return `Events: File`
      if (seriesId) return `Events: ${entityInfo.title || 'Series'}`
    }
    return 'Events'
  }

  const fetchEvents = async () => {
    try {
      setLoading(true)
      setError(null)

      // Build query params
      const params = new URLSearchParams()
      if (documentId) params.set('document_id', documentId)
      else if (fileId) params.set('file_id', fileId)
      else if (seriesId) params.set('series_id', seriesId)
      else if (entityId) params.set('id', entityId)

      if (categoryFilter !== 'all') {
        params.set('event_category', categoryFilter)
      }
      params.set('limit', '100')

      const response = await authFetch(`/api/v1/events?${params.toString()}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch events: ${response.statusText}`)
      }

      const data = await response.json()
      setEvents(data.events || [])
    } catch (err) {
      console.error('Error fetching events:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // Fetch entity info for title
  const fetchEntityInfo = async () => {
    try {
      let endpoint = null
      if (documentId) endpoint = `/api/v1/documents/${documentId}`
      else if (fileId) endpoint = `/api/v1/files/${fileId}`
      else if (seriesId) endpoint = `/api/v1/series/${seriesId}`

      if (endpoint) {
        const response = await authFetch(endpoint)
        if (response.ok) {
          const data = await response.json()
          // Handle different response structures
          if (fileId && data.file) {
            setEntityInfo(data.file)
          } else {
            setEntityInfo(data)
          }
        }
      }
    } catch (err) {
      console.error('Error fetching entity info:', err)
    }
  }

  useEffect(() => {
    fetchEvents()
    fetchEntityInfo()
  }, [entityId, documentId, fileId, seriesId, categoryFilter])

  const handleRefresh = async (event) => {
    await fetchEvents()
    event?.detail?.complete()
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  const formatRelativeTime = (dateStr) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now - date
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    if (diffSec < 60) return `${diffSec}s ago`
    if (diffMin < 60) return `${diffMin}m ago`
    if (diffHour < 24) return `${diffHour}h ago`
    return `${diffDay}d ago`
  }

  const getCategoryColor = (category) => {
    const colors = {
      'state_transition': 'primary',
      'llm_request': 'secondary',
      'processing': 'success',
      'error': 'danger',
      'user_action': 'tertiary'
    }
    return colors[category] || 'medium'
  }

  const getCategoryIcon = (category) => {
    const icons = {
      'state_transition': arrowForward,
      'llm_request': chatbubble,
      'processing': sync,
      'error': alertCircle,
      'user_action': person
    }
    return icons[category] || checkmarkCircle
  }

  const formatCategoryLabel = (category) => {
    const labels = {
      'state_transition': 'State',
      'llm_request': 'LLM',
      'processing': 'Processing',
      'error': 'Error',
      'user_action': 'User'
    }
    return labels[category] || category
  }

  const renderEventCard = (event) => {
    const isError = event.event_category === 'error'
    const isLLM = event.event_category === 'llm_request'
    const isStateTransition = event.event_category === 'state_transition'

    return (
      <IonCard key={event.id} color={isError ? 'danger' : undefined}>
        <IonCardHeader>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <IonIcon icon={getCategoryIcon(event.event_category)} />
                <IonBadge color={getCategoryColor(event.event_category)}>
                  {formatCategoryLabel(event.event_category)}
                </IonBadge>
                <span style={{ fontSize: '0.85em', fontWeight: '500' }}>
                  {event.event_type}
                </span>
              </div>
              <div style={{ fontSize: '0.75em', color: isError ? '#fff' : '#666', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <IonIcon icon={time} style={{ fontSize: '12px' }} />
                {formatDate(event.created_at)}
                <span style={{ marginLeft: '8px', opacity: 0.7 }}>
                  ({formatRelativeTime(event.created_at)})
                </span>
              </div>
            </div>
          </div>
        </IonCardHeader>

        <IonCardContent>
          {/* State Transition Details */}
          {isStateTransition && event.old_status && event.new_status && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '8px',
              padding: '8px',
              background: 'rgba(0,0,0,0.05)',
              borderRadius: '4px'
            }}>
              <IonBadge color="medium">{event.old_status}</IonBadge>
              <IonIcon icon={arrowForward} />
              <IonBadge color="success">{event.new_status}</IonBadge>
            </div>
          )}

          {/* LLM Request Details */}
          {isLLM && (
            <div style={{ marginBottom: '8px' }}>
              {event.llm_model && (
                <div style={{ fontSize: '0.85em', marginBottom: '4px' }}>
                  <strong>Model:</strong> {event.llm_model}
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', fontSize: '0.85em' }}>
                {event.llm_request_tokens && (
                  <span><strong>In:</strong> {event.llm_request_tokens} tokens</span>
                )}
                {event.llm_response_tokens && (
                  <span><strong>Out:</strong> {event.llm_response_tokens} tokens</span>
                )}
                {event.llm_latency_ms && (
                  <span><strong>Latency:</strong> {event.llm_latency_ms}ms</span>
                )}
                {event.llm_cost_usd && (
                  <span><strong>Cost:</strong> ${event.llm_cost_usd.toFixed(4)}</span>
                )}
              </div>

              {/* Expandable prompt/response */}
              {(event.llm_prompt_text || event.llm_response_text) && (
                <details style={{ marginTop: '8px' }}>
                  <summary style={{ cursor: 'pointer', fontSize: '0.85em', color: 'var(--ion-color-primary)' }}>
                    View Prompt/Response
                  </summary>
                  {event.llm_prompt_text && (
                    <div style={{ marginTop: '8px' }}>
                      <strong style={{ fontSize: '0.8em' }}>Prompt:</strong>
                      <pre style={{
                        whiteSpace: 'pre-wrap',
                        fontSize: '0.75em',
                        backgroundColor: '#f5f5f5',
                        padding: '8px',
                        borderRadius: '4px',
                        maxHeight: '150px',
                        overflow: 'auto',
                        marginTop: '4px'
                      }}>
                        {event.llm_prompt_text}
                      </pre>
                    </div>
                  )}
                  {event.llm_response_text && (
                    <div style={{ marginTop: '8px' }}>
                      <strong style={{ fontSize: '0.8em' }}>Response:</strong>
                      <pre style={{
                        whiteSpace: 'pre-wrap',
                        fontSize: '0.75em',
                        backgroundColor: '#f5f5f5',
                        padding: '8px',
                        borderRadius: '4px',
                        maxHeight: '150px',
                        overflow: 'auto',
                        marginTop: '4px'
                      }}>
                        {event.llm_response_text}
                      </pre>
                    </div>
                  )}
                </details>
              )}
            </div>
          )}

          {/* Task Name */}
          {event.task_name && (
            <div style={{ fontSize: '0.85em', marginBottom: '4px' }}>
              <strong>Task:</strong> {event.task_name}
            </div>
          )}

          {/* Error Message */}
          {event.error_message && (
            <div style={{
              padding: '8px',
              background: isError ? 'rgba(255,255,255,0.1)' : 'rgba(255,0,0,0.1)',
              borderRadius: '4px',
              marginBottom: '8px'
            }}>
              <pre style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.8em',
                margin: 0,
                color: isError ? '#fff' : '#c00'
              }}>
                {event.error_message}
              </pre>
            </div>
          )}

          {/* Details JSON */}
          {event.details && Object.keys(event.details).length > 0 && (
            <details style={{ marginTop: '8px' }}>
              <summary style={{
                cursor: 'pointer',
                fontSize: '0.85em',
                color: isError ? '#fff' : 'var(--ion-color-primary)'
              }}>
                View Details
              </summary>
              <pre style={{
                whiteSpace: 'pre-wrap',
                fontSize: '0.75em',
                backgroundColor: isError ? 'rgba(255,255,255,0.1)' : '#f5f5f5',
                padding: '8px',
                borderRadius: '4px',
                marginTop: '4px',
                maxHeight: '200px',
                overflow: 'auto'
              }}>
                {JSON.stringify(event.details, null, 2)}
              </pre>
            </details>
          )}
        </IonCardContent>
      </IonCard>
    )
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref={getBackUrl()} />
          </IonButtons>
          <IonTitle>{getPageTitle()}</IonTitle>
          <IonButton slot="end" fill="clear" onClick={fetchEvents} disabled={loading}>
            <IonIcon icon={refresh} />
          </IonButton>
        </IonToolbar>

        {/* Category Filter */}
        <IonToolbar>
          <IonSegment value={categoryFilter} onIonChange={e => setCategoryFilter(e.detail.value)}>
            <IonSegmentButton value="all">
              <IonLabel>All</IonLabel>
            </IonSegmentButton>
            <IonSegmentButton value="state_transition">
              <IonLabel>State</IonLabel>
            </IonSegmentButton>
            <IonSegmentButton value="llm_request">
              <IonLabel>LLM</IonLabel>
            </IonSegmentButton>
            <IonSegmentButton value="processing">
              <IonLabel>Process</IonLabel>
            </IonSegmentButton>
            <IonSegmentButton value="error">
              <IonLabel>Error</IonLabel>
            </IonSegmentButton>
          </IonSegment>
        </IonToolbar>
      </IonHeader>

      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent></IonRefresherContent>
        </IonRefresher>

        {loading && events.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading events...</p>
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

        {!loading && !error && events.length === 0 && (
          <IonCard>
            <IonCardContent>
              <div style={{ textAlign: 'center', padding: '20px', color: '#666' }}>
                <IonIcon icon={checkmarkCircle} style={{ fontSize: '48px', marginBottom: '12px' }} />
                <p>No events found{categoryFilter !== 'all' ? ` for category "${categoryFilter}"` : ''}.</p>
              </div>
            </IonCardContent>
          </IonCard>
        )}

        {/* Events Count */}
        {events.length > 0 && (
          <div style={{ padding: '8px 16px', fontSize: '0.85em', color: '#666' }}>
            Showing {events.length} event{events.length !== 1 ? 's' : ''}
          </div>
        )}

        {/* Events List */}
        {events.map(renderEventCard)}
      </IonContent>
    </IonPage>
  )
}

export default EventsPage

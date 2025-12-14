import { useState } from 'react'
import {
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonSearchbar,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonIcon,
  IonBadge,
  IonSpinner,
  IonList,
  IonSegment,
  IonSegmentButton,
  IonLabel
} from '@ionic/react'
import { documentText, layers, search as searchIcon } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'

function SearchPage() {
  const history = useHistory()
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [results, setResults] = useState({ documents: [], series: [] })
  const [hasSearched, setHasSearched] = useState(false)
  const [activeSegment, setActiveSegment] = useState('all')

  const performSearch = async (query) => {
    if (!query || query.trim().length === 0) {
      setResults({ documents: [], series: [] })
      setHasSearched(false)
      return
    }

    try {
      setLoading(true)
      setError(null)
      setHasSearched(true)

      const response = await fetch(
        `/api/v1/search?q=${encodeURIComponent(query)}&limit=50&include_documents=true&include_files=false&include_series=true`
      )
      if (!response.ok) {
        throw new Error(`Search failed: ${response.statusText}`)
      }

      const data = await response.json()
      setResults({
        documents: data.documents || [],
        series: data.series || []
      })
    } catch (err) {
      console.error('Error searching:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleSearchChange = (e) => {
    const query = e.detail.value
    setSearchQuery(query)
  }

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    performSearch(searchQuery)
  }

  const getStatusColor = (status) => {
    const colors = {
      'completed': 'success',
      'pending': 'warning',
      'ocr_completed': 'primary',
      'classified': 'secondary',
      'error': 'danger',
      'active': 'success',
      'archived': 'light'
    }
    return colors[status] || 'medium'
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString()
  }

  const totalResults = results.documents.length + results.series.length

  const filteredDocuments = activeSegment === 'all' || activeSegment === 'documents'
    ? results.documents
    : []
  const filteredSeries = activeSegment === 'all' || activeSegment === 'series'
    ? results.series
    : []

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <div slot="start" style={{ display: 'flex', alignItems: 'center', marginLeft: '10px' }}>
            <img src="/ALFRD.svg" alt="ALFRD Logo" style={{ height: '32px', width: 'auto' }} />
          </div>
          <IonTitle>Search</IonTitle>
        </IonToolbar>
        <IonToolbar>
          <form onSubmit={handleSearchSubmit}>
            <IonSearchbar
              value={searchQuery}
              onIonInput={handleSearchChange}
              onIonClear={() => {
                setResults({ documents: [], series: [] })
                setHasSearched(false)
              }}
              placeholder="Search documents and series..."
              showClearButton="always"
              enterkeyhint="search"
            />
          </form>
        </IonToolbar>
        {hasSearched && totalResults > 0 && (
          <IonToolbar>
            <IonSegment value={activeSegment} onIonChange={(e) => setActiveSegment(e.detail.value)}>
              <IonSegmentButton value="all">
                <IonLabel>All ({totalResults})</IonLabel>
              </IonSegmentButton>
              <IonSegmentButton value="documents">
                <IonLabel>Documents ({results.documents.length})</IonLabel>
              </IonSegmentButton>
              <IonSegmentButton value="series">
                <IonLabel>Series ({results.series.length})</IonLabel>
              </IonSegmentButton>
            </IonSegment>
          </IonToolbar>
        )}
      </IonHeader>

      <IonContent>
        {!hasSearched && !loading && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#666' }}>
            <IonIcon icon={searchIcon} style={{ fontSize: '64px', marginBottom: '16px', opacity: 0.5 }} />
            <p style={{ fontSize: '1.1em' }}>Search across your documents and series</p>
            <p style={{ fontSize: '0.9em', color: '#999' }}>
              Enter keywords to find matching documents and recurring series
            </p>
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Searching...</p>
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

        {hasSearched && !loading && !error && totalResults === 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>No Results</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              <p>No documents or series match your search query. Try different keywords.</p>
            </IonCardContent>
          </IonCard>
        )}

        {!loading && !error && (
          <IonList>
            {/* Documents Section */}
            {filteredDocuments.length > 0 && (
              <>
                {activeSegment === 'all' && (
                  <div style={{ padding: '16px 16px 8px', fontWeight: '600', color: '#666' }}>
                    Documents ({results.documents.length})
                  </div>
                )}
                {filteredDocuments.map((doc) => (
                  <IonCard
                    key={`doc-${doc.id}`}
                    button
                    onClick={() => history.push(`/documents/${doc.id}`)}
                    style={{ margin: '10px' }}
                  >
                    <IonCardHeader>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <IonCardTitle style={{ fontSize: '1.1em', marginBottom: '4px' }}>
                            <IonIcon icon={documentText} style={{ marginRight: '8px', color: '#3880ff' }} />
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
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                        {doc.document_type && (
                          <IonBadge color="primary" style={{ marginRight: '4px' }}>
                            {doc.document_type}
                          </IonBadge>
                        )}
                        {doc.tags && doc.tags.length > 0 && (
                          doc.tags.slice(0, 3).map((tag, idx) => (
                            <IonBadge key={idx} color="secondary" style={{ marginRight: '4px' }}>
                              {tag}
                            </IonBadge>
                          ))
                        )}
                        {doc.tags && doc.tags.length > 3 && (
                          <IonBadge color="light">+{doc.tags.length - 3}</IonBadge>
                        )}
                      </div>
                    </IonCardContent>
                  </IonCard>
                ))}
              </>
            )}

            {/* Series Section */}
            {filteredSeries.length > 0 && (
              <>
                {activeSegment === 'all' && (
                  <div style={{ padding: '16px 16px 8px', fontWeight: '600', color: '#666' }}>
                    Series ({results.series.length})
                  </div>
                )}
                {filteredSeries.map((s) => (
                  <IonCard
                    key={`series-${s.id}`}
                    button
                    onClick={() => history.push(`/series/${s.id}`)}
                    style={{ margin: '10px' }}
                  >
                    <IonCardHeader>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <IonCardTitle style={{ fontSize: '1.1em', marginBottom: '4px' }}>
                            <IonIcon icon={layers} style={{ marginRight: '8px', color: '#5260ff' }} />
                            {s.title}
                          </IonCardTitle>
                          <p style={{ fontSize: '0.85em', color: '#666', margin: '0 0 4px 0' }}>
                            {s.entity}
                          </p>
                          {s.description && (
                            <p style={{ fontSize: '0.8em', color: '#999', margin: '0 0 8px 0' }}>
                              {s.description}
                            </p>
                          )}
                        </div>
                        <IonBadge color={getStatusColor(s.status)}>
                          {s.status}
                        </IonBadge>
                      </div>
                    </IonCardHeader>
                    <IonCardContent>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center', marginBottom: '8px' }}>
                        <IonBadge color="primary">
                          {s.series_type?.replace(/_/g, ' ')}
                        </IonBadge>
                        {s.frequency && (
                          <IonBadge color="secondary">
                            {s.frequency}
                          </IonBadge>
                        )}
                        <IonBadge color="light" style={{ marginLeft: 'auto' }}>
                          {s.document_count || 0} docs
                        </IonBadge>
                      </div>
                      {s.first_document_date && s.last_document_date && (
                        <p style={{ fontSize: '0.75em', color: '#999', margin: 0 }}>
                          {formatDate(s.first_document_date)} - {formatDate(s.last_document_date)}
                        </p>
                      )}
                    </IonCardContent>
                  </IonCard>
                ))}
              </>
            )}
          </IonList>
        )}
      </IonContent>
    </IonPage>
  )
}

export default SearchPage

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
  IonSelect,
  IonSelectOption
} from '@ionic/react'
import { refresh, close, layers } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

function SeriesPage() {
  const history = useHistory()
  const { authFetch } = useAuth()
  const [series, setSeries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [frequencyFilter, setFrequencyFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const fetchSeries = async () => {
    try {
      setLoading(true)
      setError(null)

      // Build query params
      const params = new URLSearchParams({ limit: '50' })
      if (frequencyFilter) params.append('frequency', frequencyFilter)
      if (statusFilter) params.append('status', statusFilter)

      const response = await authFetch(`/api/v1/series?${params}`)
      if (!response.ok) {
        throw new Error(`Failed to fetch series: ${response.statusText}`)
      }

      const data = await response.json()
      setSeries(data.series || [])
    } catch (err) {
      console.error('Error fetching series:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSeries()
  }, [frequencyFilter, statusFilter])

  const handleRefresh = async (event) => {
    await fetchSeries()
    event?.detail?.complete()
  }

  const clearFilters = () => {
    setFrequencyFilter('')
    setStatusFilter('')
  }

  const getStatusColor = (status) => {
    const colors = {
      'active': 'success',
      'completed': 'medium',
      'archived': 'light'
    }
    return colors[status] || 'medium'
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString()
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <div slot="start" style={{ display: 'flex', alignItems: 'center', marginLeft: '10px' }}>
            <img src="/ALFRD.svg" alt="ALFRD Logo" style={{ height: '32px', width: 'auto' }} />
          </div>
          <IonTitle>Series</IonTitle>
          <IonButton slot="end" fill="clear" onClick={fetchSeries}>
            <IonIcon icon={refresh} />
          </IonButton>
        </IonToolbar>
        <IonToolbar>
          <div style={{ display: 'flex', gap: '8px', padding: '8px' }}>
            <IonSelect
              value={frequencyFilter}
              placeholder="Frequency"
              onIonChange={(e) => setFrequencyFilter(e.detail.value)}
              style={{ flex: 1 }}
            >
              <IonSelectOption value="">All Frequencies</IonSelectOption>
              <IonSelectOption value="monthly">Monthly</IonSelectOption>
              <IonSelectOption value="quarterly">Quarterly</IonSelectOption>
              <IonSelectOption value="annual">Annual</IonSelectOption>
              <IonSelectOption value="weekly">Weekly</IonSelectOption>
            </IonSelect>

            <IonSelect
              value={statusFilter}
              placeholder="Status"
              onIonChange={(e) => setStatusFilter(e.detail.value)}
              style={{ flex: 1 }}
            >
              <IonSelectOption value="">All Statuses</IonSelectOption>
              <IonSelectOption value="active">Active</IonSelectOption>
              <IonSelectOption value="completed">Completed</IonSelectOption>
              <IonSelectOption value="archived">Archived</IonSelectOption>
            </IonSelect>

            {(frequencyFilter || statusFilter) && (
              <IonButton fill="clear" onClick={clearFilters}>
                <IonIcon icon={close} />
              </IonButton>
            )}
          </div>
        </IonToolbar>
      </IonHeader>

      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent></IonRefresherContent>
        </IonRefresher>

        {loading && (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <IonSpinner name="crescent" />
            <p>Loading series...</p>
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

        {!loading && !error && series.length === 0 && (
          <IonCard>
            <IonCardHeader>
              <IonCardTitle>{frequencyFilter || statusFilter ? 'No Results' : 'No Series'}</IonCardTitle>
            </IonCardHeader>
            <IonCardContent>
              {frequencyFilter || statusFilter ? (
                <p>No series match your filters. Try adjusting your filters.</p>
              ) : (
                <p>No series found yet. Upload recurring documents to automatically create series.</p>
              )}
            </IonCardContent>
          </IonCard>
        )}

        {!loading && !error && series.length > 0 && (
          <IonList>
            {series.map((s) => (
              <IonCard
                key={s.id}
                button
                onClick={() => history.push(`/series/${s.id}`)}
                style={{ margin: '10px' }}
              >
                <IonCardHeader>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <IonCardTitle style={{ fontSize: '1.1em', marginBottom: '4px' }}>
                        <IonIcon icon={layers} style={{ marginRight: '8px' }} />
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
          </IonList>
        )}
      </IonContent>
    </IonPage>
  )
}

export default SeriesPage

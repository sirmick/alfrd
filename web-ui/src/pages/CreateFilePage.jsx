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
  IonList,
  IonItem,
  IonCheckbox,
  IonLabel,
  IonBackButton,
  IonButtons,
  IonInput,
  IonChip,
  IonToast,
  IonSelect,
  IonSelectOption
} from '@ionic/react'
import { arrowBack, add, checkmark, close } from 'ionicons/icons'
import { useHistory } from 'react-router-dom'

function CreateFilePage() {
  const history = useHistory()
  const [step, setStep] = useState(1)
  const [documents, setDocuments] = useState([])
  const [selectedDocIds, setSelectedDocIds] = useState([])
  const [documentType, setDocumentType] = useState('bill')
  const [tags, setTags] = useState([])
  const [tagInput, setTagInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState({ show: false, message: '' })

  useEffect(() => {
    fetchDocuments()
  }, [])

  const fetchDocuments = async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/v1/documents?limit=100&status=completed')
      if (!response.ok) {
        throw new Error('Failed to fetch documents')
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

  const handleDocumentToggle = (docId) => {
    setSelectedDocIds(prev => 
      prev.includes(docId) 
        ? prev.filter(id => id !== docId)
        : [...prev, docId]
    )
  }

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()])
      setTagInput('')
    }
  }

  const handleRemoveTag = (tag) => {
    setTags(tags.filter(t => t !== tag))
  }

  const handleCreate = async () => {
    if (selectedDocIds.length === 0) {
      setToast({ show: true, message: 'Please select at least one document' })
      return
    }

    if (tags.length === 0) {
      setToast({ show: true, message: 'Please add at least one tag' })
      return
    }

    try {
      setLoading(true)
      
      // Build query string (all parameters must be in the URL for FastAPI Query params)
      const params = new URLSearchParams()
      params.append('document_type', documentType)
      tags.forEach(tag => params.append('tags', tag))
      selectedDocIds.forEach(id => params.append('document_ids', id))

      const url = `/api/v1/files/create?${params.toString()}`
      console.log('Creating file with URL:', url)

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('API error:', errorText)
        throw new Error(`Failed to create file: ${response.statusText}`)
      }

      const data = await response.json()
      
      setToast({ show: true, message: 'File created successfully!' })
      
      // Navigate to file detail after a short delay
      setTimeout(() => {
        history.push(`/files/${data.file.id}`)
      }, 1000)
      
    } catch (err) {
      console.error('Error creating file:', err)
      setToast({ show: true, message: `Error: ${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString()
  }

  const getSuggestedTags = () => {
    const selectedDocs = documents.filter(doc => selectedDocIds.includes(doc.id))
    const tagCounts = {}
    
    selectedDocs.forEach(doc => {
      if (doc.secondary_tags && Array.isArray(doc.secondary_tags)) {
        doc.secondary_tags.forEach(tag => {
          tagCounts[tag] = (tagCounts[tag] || 0) + 1
        })
      }
    })

    // Return tags that appear in at least half of selected documents
    const threshold = Math.ceil(selectedDocs.length / 2)
    return Object.entries(tagCounts)
      .filter(([tag, count]) => count >= threshold)
      .map(([tag]) => tag)
  }

  const renderStep1 = () => (
    <>
      <IonCard>
        <IonCardHeader>
          <IonCardTitle>Select Documents</IonCardTitle>
        </IonCardHeader>
        <IonCardContent>
          <p>Choose documents to include in this file</p>
          <p style={{ marginTop: '8px', color: '#666', fontSize: '0.9em' }}>
            {selectedDocIds.length} selected
          </p>
        </IonCardContent>
      </IonCard>

      {loading && (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <IonSpinner name="crescent" />
        </div>
      )}

      {!loading && documents.length === 0 && (
        <IonCard>
          <IonCardContent>
            <p>No completed documents available. Please process some documents first.</p>
          </IonCardContent>
        </IonCard>
      )}

      {!loading && documents.length > 0 && (
        <IonList>
          {documents.map((doc) => (
            <IonItem key={doc.id} button onClick={() => handleDocumentToggle(doc.id)}>
              <IonCheckbox
                slot="start"
                checked={selectedDocIds.includes(doc.id)}
                onIonChange={() => handleDocumentToggle(doc.id)}
              />
              <IonLabel>
                <h3>{doc.summary || doc.document_type || 'Untitled'}</h3>
                <p>{formatDate(doc.created_at)}</p>
                {doc.document_type && (
                  <div style={{ marginTop: '4px' }}>
                    <IonBadge color="primary">{doc.document_type}</IonBadge>
                    {doc.secondary_tags && doc.secondary_tags.length > 0 && doc.secondary_tags.slice(0, 3).map((tag, idx) => (
                      <IonBadge key={idx} color="secondary" style={{ marginLeft: '4px' }}>
                        {tag}
                      </IonBadge>
                    ))}
                  </div>
                )}
              </IonLabel>
            </IonItem>
          ))}
        </IonList>
      )}

      <div style={{ padding: '16px' }}>
        <IonButton
          expand="block"
          onClick={() => setStep(2)}
          disabled={selectedDocIds.length === 0}
        >
          Next: Choose Tags
        </IonButton>
      </div>
    </>
  )

  const renderStep2 = () => {
    const suggestedTags = getSuggestedTags()

    return (
      <>
        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Configure File</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            <p>Set the document type and tags for this file</p>
          </IonCardContent>
        </IonCard>

        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Document Type</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            <IonSelect
              value={documentType}
              onIonChange={(e) => setDocumentType(e.detail.value)}
              interface="action-sheet"
              style={{ width: '100%' }}
            >
              <IonSelectOption value="bill">Bill</IonSelectOption>
              <IonSelectOption value="finance">Finance</IonSelectOption>
              <IonSelectOption value="school">School</IonSelectOption>
              <IonSelectOption value="event">Event</IonSelectOption>
              <IonSelectOption value="junk">Junk</IonSelectOption>
              <IonSelectOption value="generic">Generic</IonSelectOption>
            </IonSelect>
          </IonCardContent>
        </IonCard>

        <IonCard>
          <IonCardHeader>
            <IonCardTitle>Tags</IonCardTitle>
          </IonCardHeader>
          <IonCardContent>
            {tags.length > 0 && (
              <div style={{ marginBottom: '16px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {tags.map((tag) => (
                  <IonChip key={tag} onClick={() => handleRemoveTag(tag)}>
                    <IonLabel>{tag}</IonLabel>
                    <IonIcon icon={close} />
                  </IonChip>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <IonInput
                value={tagInput}
                placeholder="Enter tag name"
                onIonInput={(e) => setTagInput(e.detail.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAddTag()}
                style={{ border: '1px solid #ddd', borderRadius: '4px', padding: '8px' }}
              />
              <IonButton onClick={handleAddTag} disabled={!tagInput.trim()}>
                <IonIcon icon={add} />
              </IonButton>
            </div>

            {suggestedTags.length > 0 && (
              <div>
                <p style={{ fontSize: '0.9em', color: '#666', marginBottom: '8px' }}>
                  Suggested (from selected documents):
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {suggestedTags.map((tag) => (
                    <IonChip
                      key={tag}
                      color="primary"
                      outline
                      onClick={() => {
                        if (!tags.includes(tag)) {
                          setTags([...tags, tag])
                        }
                      }}
                      disabled={tags.includes(tag)}
                    >
                      <IonLabel>{tag}</IonLabel>
                      <IonIcon icon={add} />
                    </IonChip>
                  ))}
                </div>
              </div>
            )}

            <p style={{ fontSize: '0.85em', color: '#666', marginTop: '16px' }}>
              File signature: {documentType}:{tags.join(':')}
            </p>
          </IonCardContent>
        </IonCard>

        <div style={{ padding: '16px', display: 'flex', gap: '8px' }}>
          <IonButton
            expand="block"
            fill="outline"
            onClick={() => setStep(1)}
            style={{ flex: 1 }}
          >
            Back
          </IonButton>
          <IonButton
            expand="block"
            onClick={handleCreate}
            disabled={tags.length === 0 || loading}
            style={{ flex: 1 }}
          >
            {loading ? <IonSpinner name="crescent" /> : 'Create File'}
          </IonButton>
        </div>
      </>
    )
  }

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonButtons slot="start">
            <IonBackButton defaultHref="/files" />
          </IonButtons>
          <IonTitle>Create File</IonTitle>
        </IonToolbar>
      </IonHeader>
      
      <IonContent>
        {error && (
          <IonCard color="danger">
            <IonCardContent>{error}</IonCardContent>
          </IonCard>
        )}

        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}

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

export default CreateFilePage
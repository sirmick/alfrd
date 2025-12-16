import React, { useState, useEffect } from 'react';
import {
  IonPage,
  IonHeader,
  IonToolbar,
  IonTitle,
  IonContent,
  IonList,
  IonItem,
  IonLabel,
  IonBadge,
  IonButton,
  IonModal,
  IonTextarea,
  IonSelect,
  IonSelectOption,
  IonSearchbar,
  IonRefresher,
  IonRefresherContent,
  IonChip,
  IonIcon,
  IonCard,
  IonCardHeader,
  IonCardTitle,
  IonCardContent,
  IonGrid,
  IonRow,
  IonCol,
  IonSpinner,
  IonToast,
} from '@ionic/react';
import {
  createOutline,
  checkmarkCircle,
  closeCircle,
  trendingUpOutline,
  documentTextOutline,
  addOutline,
} from 'ionicons/icons';
import { useAuth } from '../context/AuthContext';

const API_BASE = '/api/v1';

const PromptsPage = () => {
  const { authFetch } = useAuth();
  const [prompts, setPrompts] = useState([]);
  const [documentTypes, setDocumentTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [showEditor, setShowEditor] = useState(false);
  const [filterType, setFilterType] = useState('all');
  const [searchText, setSearchText] = useState('');
  const [showToast, setShowToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [includeInactive, setIncludeInactive] = useState(false);

  // Editor state
  const [editorPromptType, setEditorPromptType] = useState('classifier');
  const [editorDocType, setEditorDocType] = useState('');
  const [editorText, setEditorText] = useState('');

  useEffect(() => {
    loadPrompts();
    loadDocumentTypes();
  }, [filterType, includeInactive]);

  const loadPrompts = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterType !== 'all') {
        params.append('prompt_type', filterType);
      }
      params.append('include_inactive', includeInactive);

      const response = await authFetch(`${API_BASE}/prompts?${params}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setPrompts(data.prompts || []);
    } catch (error) {
      console.error('Error loading prompts:', error);
      setToastMessage(`Error loading prompts: ${error.message}`);
      setShowToast(true);
      setPrompts([]);
    } finally {
      setLoading(false);
    }
  };

  const loadDocumentTypes = async () => {
    try {
      const response = await authFetch(`${API_BASE}/document-types`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setDocumentTypes(data.document_types || []);
    } catch (error) {
      console.error('Error loading document types:', error);
      setDocumentTypes([]);
    }
  };

  const handleRefresh = async (event) => {
    await loadPrompts();
    event.detail.complete();
  };

  const openEditor = (prompt = null) => {
    if (prompt) {
      setSelectedPrompt(prompt);
      setEditorPromptType(prompt.prompt_type);
      setEditorDocType(prompt.document_type || '');
      setEditorText(prompt.prompt_text);
    } else {
      setSelectedPrompt(null);
      setEditorPromptType('classifier');
      setEditorDocType('');
      setEditorText('');
    }
    setShowEditor(true);
  };

  const savePrompt = async () => {
    try {
      const params = new URLSearchParams();
      params.append('prompt_type', editorPromptType);
      params.append('prompt_text', editorText);
      if (editorPromptType === 'summarizer' && editorDocType) {
        params.append('document_type', editorDocType);
      }

      const response = await authFetch(`${API_BASE}/prompts?${params}`, {
        method: 'POST',
      });

      if (response.ok) {
        setToastMessage('Prompt created successfully');
        setShowToast(true);
        setShowEditor(false);
        loadPrompts();
      } else {
        const error = await response.json();
        setToastMessage(`Error: ${error.detail}`);
        setShowToast(true);
      }
    } catch (error) {
      console.error('Error saving prompt:', error);
      setToastMessage('Error saving prompt');
      setShowToast(true);
    }
  };

  const filteredPrompts = prompts.filter((prompt) => {
    if (!searchText) return true;
    const searchLower = searchText.toLowerCase();
    return (
      prompt.prompt_type.toLowerCase().includes(searchLower) ||
      (prompt.document_type && prompt.document_type.toLowerCase().includes(searchLower)) ||
      prompt.prompt_text.toLowerCase().includes(searchLower)
    );
  });

  const getTypeColor = (type) => {
    const colors = {
      classifier: 'primary',
      summarizer: 'success',
      file_summarizer: 'warning',
      series_detector: 'tertiary',
    };
    return colors[type] || 'medium';
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <IonPage>
      <IonHeader>
        <IonToolbar>
          <IonTitle>Prompt Management</IonTitle>
        </IonToolbar>
      </IonHeader>

      <IonContent>
        <IonRefresher slot="fixed" onIonRefresh={handleRefresh}>
          <IonRefresherContent />
        </IonRefresher>

        {/* Summary Cards */}
        <IonGrid>
          <IonRow>
            <IonCol size="6">
              <IonCard>
                <IonCardContent className="ion-text-center">
                  <h2>{prompts.filter(p => p.is_active).length}</h2>
                  <p>Active Prompts</p>
                </IonCardContent>
              </IonCard>
            </IonCol>
            <IonCol size="6">
              <IonCard>
                <IonCardContent className="ion-text-center">
                  <h2>{documentTypes.length}</h2>
                  <p>Document Types</p>
                </IonCardContent>
              </IonCard>
            </IonCol>
          </IonRow>
        </IonGrid>

        {/* Filter Controls */}
        <IonCard>
          <IonCardContent>
            <IonSearchbar
              value={searchText}
              onIonInput={(e) => setSearchText(e.detail.value)}
              placeholder="Search prompts..."
            />

            <IonGrid>
              <IonRow>
                <IonCol>
                  <IonSelect
                    value={filterType}
                    placeholder="Filter by Type"
                    onIonChange={(e) => setFilterType(e.detail.value)}
                  >
                    <IonSelectOption value="all">All Types</IonSelectOption>
                    <IonSelectOption value="classifier">Classifier</IonSelectOption>
                    <IonSelectOption value="summarizer">Summarizer</IonSelectOption>
                    <IonSelectOption value="file_summarizer">File Summarizer</IonSelectOption>
                    <IonSelectOption value="series_detector">Series Detector</IonSelectOption>
                  </IonSelect>
                </IonCol>
                <IonCol>
                  <IonButton
                    expand="block"
                    fill={includeInactive ? 'solid' : 'outline'}
                    onClick={() => setIncludeInactive(!includeInactive)}
                  >
                    {includeInactive ? 'All Versions' : 'Active Only'}
                  </IonButton>
                </IonCol>
              </IonRow>
            </IonGrid>

            <IonButton expand="block" onClick={() => openEditor()}>
              <IonIcon icon={addOutline} slot="start" />
              Create New Prompt
            </IonButton>
          </IonCardContent>
        </IonCard>

        {/* Prompts List */}
        {loading ? (
          <div className="ion-text-center ion-padding">
            <IonSpinner />
          </div>
        ) : (
          <IonList>
            {filteredPrompts.map((prompt) => (
              <IonCard key={prompt.id}>
                <IonCardHeader>
                  <IonCardTitle>
                    <IonBadge color={getTypeColor(prompt.prompt_type)}>
                      {prompt.prompt_type}
                    </IonBadge>
                    {prompt.document_type && (
                      <IonBadge color="medium" style={{ marginLeft: '8px' }}>
                        {prompt.document_type}
                      </IonBadge>
                    )}
                    <IonBadge color="light" style={{ marginLeft: '8px' }}>
                      v{prompt.version}
                    </IonBadge>
                    {prompt.is_active ? (
                      <IonIcon
                        icon={checkmarkCircle}
                        color="success"
                        style={{ marginLeft: '8px' }}
                      />
                    ) : (
                      <IonIcon
                        icon={closeCircle}
                        color="medium"
                        style={{ marginLeft: '8px' }}
                      />
                    )}
                  </IonCardTitle>
                </IonCardHeader>

                <IonCardContent>
                  <p style={{
                    fontSize: '0.9em',
                    color: 'var(--ion-color-medium)',
                    maxHeight: '60px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}>
                    {prompt.prompt_text.substring(0, 200)}...
                  </p>

                  <div style={{ marginTop: '12px', display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    {prompt.performance_score && (
                      <IonChip>
                        <IonIcon icon={trendingUpOutline} />
                        <IonLabel>Score: {prompt.performance_score.toFixed(2)}</IonLabel>
                      </IonChip>
                    )}
                    <IonChip>
                      <IonLabel>Created: {formatDate(prompt.created_at)}</IonLabel>
                    </IonChip>
                  </div>

                  <IonButton
                    size="small"
                    fill="outline"
                    onClick={() => openEditor(prompt)}
                    style={{ marginTop: '8px' }}
                  >
                    <IonIcon icon={documentTextOutline} slot="start" />
                    View Details
                  </IonButton>
                </IonCardContent>
              </IonCard>
            ))}

            {filteredPrompts.length === 0 && !loading && (
              <div className="ion-text-center ion-padding">
                <p>No prompts found</p>
              </div>
            )}
          </IonList>
        )}

        {/* Editor Modal */}
        <IonModal isOpen={showEditor} onDidDismiss={() => setShowEditor(false)}>
          <IonHeader>
            <IonToolbar>
              <IonTitle>
                {selectedPrompt ? 'View Prompt' : 'Create New Prompt'}
              </IonTitle>
              <IonButton slot="end" onClick={() => setShowEditor(false)}>
                Close
              </IonButton>
            </IonToolbar>
          </IonHeader>

          <IonContent>
            <div style={{ padding: '16px' }}>
              <IonItem>
                <IonLabel position="stacked">Prompt Type</IonLabel>
                <IonSelect
                  value={editorPromptType}
                  onIonChange={(e) => setEditorPromptType(e.detail.value)}
                  disabled={!!selectedPrompt}
                >
                  <IonSelectOption value="classifier">Classifier</IonSelectOption>
                  <IonSelectOption value="summarizer">Summarizer</IonSelectOption>
                  <IonSelectOption value="file_summarizer">File Summarizer</IonSelectOption>
                  <IonSelectOption value="series_detector">Series Detector</IonSelectOption>
                </IonSelect>
              </IonItem>

              {editorPromptType === 'summarizer' && (
                <IonItem>
                  <IonLabel position="stacked">Document Type</IonLabel>
                  <IonSelect
                    value={editorDocType}
                    onIonChange={(e) => setEditorDocType(e.detail.value)}
                    disabled={!!selectedPrompt}
                  >
                    {documentTypes.map((dt) => (
                      <IonSelectOption key={dt.type_name} value={dt.type_name}>
                        {dt.type_name}
                      </IonSelectOption>
                    ))}
                  </IonSelect>
                </IonItem>
              )}

              <IonItem>
                <IonLabel position="stacked">Prompt Text</IonLabel>
                <IonTextarea
                  value={editorText}
                  onIonInput={(e) => setEditorText(e.detail.value)}
                  rows={20}
                  placeholder="Enter prompt text..."
                  disabled={!!selectedPrompt}
                  style={{
                    fontFamily: 'monospace',
                    fontSize: '0.9em',
                    marginTop: '8px',
                  }}
                />
              </IonItem>

              {selectedPrompt && (
                <>
                  <IonCard>
                    <IonCardHeader>
                      <IonCardTitle>Metadata</IonCardTitle>
                    </IonCardHeader>
                    <IonCardContent>
                      <p><strong>Version:</strong> {selectedPrompt.version}</p>
                      <p><strong>Status:</strong> {selectedPrompt.is_active ? 'Active' : 'Inactive'}</p>
                      {selectedPrompt.performance_score && (
                        <p><strong>Performance Score:</strong> {selectedPrompt.performance_score.toFixed(3)}</p>
                      )}
                      <p><strong>Created:</strong> {formatDate(selectedPrompt.created_at)}</p>
                      <p><strong>Updated:</strong> {formatDate(selectedPrompt.updated_at)}</p>
                    </IonCardContent>
                  </IonCard>
                </>
              )}

              {!selectedPrompt && (
                <IonButton
                  expand="block"
                  onClick={savePrompt}
                  style={{ marginTop: '16px' }}
                >
                  Create Prompt
                </IonButton>
              )}
            </div>
          </IonContent>
        </IonModal>

        <IonToast
          isOpen={showToast}
          onDidDismiss={() => setShowToast(false)}
          message={toastMessage}
          duration={3000}
        />
      </IonContent>
    </IonPage>
  );
};

export default PromptsPage;
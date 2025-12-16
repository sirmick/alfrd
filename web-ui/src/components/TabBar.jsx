import { IonTabs, IonTabBar, IonTabButton, IonIcon, IonLabel, IonRouterOutlet, IonSpinner, IonPage, IonContent } from '@ionic/react'
import { Route, Redirect, Switch } from 'react-router-dom'
import { documentText, folder, camera, layers, cog, search, chatbubbles } from 'ionicons/icons'

import { useAuth } from '../context/AuthContext'
import CapturePage from '../pages/CapturePage'
import DocumentsPage from '../pages/DocumentsPage'
import DocumentDetailPage from '../pages/DocumentDetailPage'
import FilesPage from '../pages/FilesPage'
import FileDetailPage from '../pages/FileDetailPage'
import CreateFilePage from '../pages/CreateFilePage'
import SeriesPage from '../pages/SeriesPage'
import SeriesDetailPage from '../pages/SeriesDetailPage'
import PromptsPage from '../pages/PromptsPage'
import SearchPage from '../pages/SearchPage'
import ChatPage from '../pages/ChatPage'
import EventsPage from '../pages/EventsPage'
import LoginPage from '../pages/LoginPage'

// Protected route wrapper
function ProtectedRoute({ component: Component, ...rest }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <IonPage>
        <IonContent className="ion-padding">
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <IonSpinner />
          </div>
        </IonContent>
      </IonPage>
    );
  }

  return (
    <Route
      {...rest}
      render={(props) =>
        isAuthenticated ? (
          <Component {...props} />
        ) : (
          <Redirect to="/login" />
        )
      }
    />
  );
}

function TabBar() {
  const { isAuthenticated, loading } = useAuth();

  // Show loading spinner while checking auth
  if (loading) {
    return (
      <IonPage>
        <IonContent className="ion-padding">
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <IonSpinner />
          </div>
        </IonContent>
      </IonPage>
    );
  }

  // Show login page without tabs if not authenticated
  if (!isAuthenticated) {
    return (
      <Switch>
        <Route exact path="/login" component={LoginPage} />
        <Redirect to="/login" />
      </Switch>
    );
  }

  return (
    <IonTabs>
      <IonRouterOutlet>
        <Switch>
          <Route exact path="/login" component={LoginPage} />
          <ProtectedRoute exact path="/capture" component={CapturePage} />
          <ProtectedRoute exact path="/documents" component={DocumentsPage} />
          <ProtectedRoute exact path="/documents/:id" component={DocumentDetailPage} />
          <ProtectedRoute exact path="/files" component={FilesPage} />
          <ProtectedRoute exact path="/files/create" component={CreateFilePage} />
          <ProtectedRoute exact path="/files/:id" component={FileDetailPage} />
          <ProtectedRoute exact path="/series" component={SeriesPage} />
          <ProtectedRoute exact path="/series/:id" component={SeriesDetailPage} />
          <ProtectedRoute exact path="/prompts" component={PromptsPage} />
          <ProtectedRoute exact path="/search" component={SearchPage} />
          <ProtectedRoute exact path="/chat" component={ChatPage} />
          <ProtectedRoute exact path="/events" component={EventsPage} />
          <Route exact path="/">
            <Redirect to="/documents" />
          </Route>
        </Switch>
      </IonRouterOutlet>

      <IonTabBar slot="bottom">
        <IonTabButton tab="documents" href="/documents">
          <IonIcon icon={documentText} />
          <IonLabel>Docs</IonLabel>
        </IonTabButton>

        <IonTabButton tab="files" href="/files">
          <IonIcon icon={folder} />
          <IonLabel>Files</IonLabel>
        </IonTabButton>

        <IonTabButton tab="series" href="/series">
          <IonIcon icon={layers} />
          <IonLabel>Series</IonLabel>
        </IonTabButton>

        <IonTabButton tab="search" href="/search">
          <IonIcon icon={search} />
          <IonLabel>Search</IonLabel>
        </IonTabButton>

        <IonTabButton tab="chat" href="/chat">
          <IonIcon icon={chatbubbles} />
          <IonLabel>Chat</IonLabel>
        </IonTabButton>

        <IonTabButton tab="capture" href="/capture">
          <IonIcon icon={camera} />
          <IonLabel>Capture</IonLabel>
        </IonTabButton>

        <IonTabButton tab="prompts" href="/prompts">
          <IonIcon icon={cog} />
          <IonLabel>Settings</IonLabel>
        </IonTabButton>
      </IonTabBar>
    </IonTabs>
  )
}

export default TabBar

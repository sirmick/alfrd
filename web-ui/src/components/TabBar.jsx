import { IonTabs, IonTabBar, IonTabButton, IonIcon, IonLabel, IonRouterOutlet } from '@ionic/react'
import { Route, Redirect, Switch } from 'react-router-dom'
import { documentText, folder, camera, layers, cog, search } from 'ionicons/icons'

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

function TabBar() {
  return (
    <IonTabs>
      <IonRouterOutlet>
        <Switch>
          <Route exact path="/capture" component={CapturePage} />
          <Route exact path="/documents" component={DocumentsPage} />
          <Route exact path="/documents/:id" component={DocumentDetailPage} />
          <Route exact path="/files" component={FilesPage} />
          <Route exact path="/files/create" component={CreateFilePage} />
          <Route exact path="/files/:id" component={FileDetailPage} />
          <Route exact path="/series" component={SeriesPage} />
          <Route exact path="/series/:id" component={SeriesDetailPage} />
          <Route exact path="/prompts" component={PromptsPage} />
          <Route exact path="/search" component={SearchPage} />
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

        <IonTabButton tab="series" href="/series">
          <IonIcon icon={layers} />
          <IonLabel>Series</IonLabel>
        </IonTabButton>

        <IonTabButton tab="search" href="/search">
          <IonIcon icon={search} />
          <IonLabel>Search</IonLabel>
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

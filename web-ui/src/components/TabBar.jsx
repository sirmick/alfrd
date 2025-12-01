import { IonTabs, IonTabBar, IonTabButton, IonIcon, IonLabel, IonRouterOutlet } from '@ionic/react'
import { Route, Redirect, Switch } from 'react-router-dom'
import { documentText, folder, camera } from 'ionicons/icons'

import CapturePage from '../pages/CapturePage'
import DocumentsPage from '../pages/DocumentsPage'
import DocumentDetailPage from '../pages/DocumentDetailPage'
import FilesPage from '../pages/FilesPage'
import FileDetailPage from '../pages/FileDetailPage'
import CreateFilePage from '../pages/CreateFilePage'

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
          <Route exact path="/">
            <Redirect to="/documents" />
          </Route>
        </Switch>
      </IonRouterOutlet>

      <IonTabBar slot="bottom">
        <IonTabButton tab="documents" href="/documents">
          <IonIcon icon={documentText} />
          <IonLabel>Documents</IonLabel>
        </IonTabButton>

        <IonTabButton tab="files" href="/files">
          <IonIcon icon={folder} />
          <IonLabel>Files</IonLabel>
        </IonTabButton>

        <IonTabButton tab="capture" href="/capture">
          <IonIcon icon={camera} />
          <IonLabel>Capture</IonLabel>
        </IonTabButton>
      </IonTabBar>
    </IonTabs>
  )
}

export default TabBar
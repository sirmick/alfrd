import { IonApp, IonRouterOutlet, setupIonicReact } from '@ionic/react'
import { IonReactRouter } from '@ionic/react-router'
import { Route, Redirect } from 'react-router-dom'

import CapturePage from './pages/CapturePage'
import DocumentsPage from './pages/DocumentsPage'
import DocumentDetailPage from './pages/DocumentDetailPage'

// Initialize Ionic
setupIonicReact()

function App() {
  return (
    <IonApp>
      <IonReactRouter>
        <IonRouterOutlet>
          <Route exact path="/capture" component={CapturePage} />
          <Route exact path="/documents" component={DocumentsPage} />
          <Route exact path="/documents/:id" component={DocumentDetailPage} />
          <Route exact path="/">
            <Redirect to="/documents" />
          </Route>
        </IonRouterOutlet>
      </IonReactRouter>
    </IonApp>
  )
}

export default App
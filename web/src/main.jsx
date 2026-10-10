import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Client as Styletron } from 'styletron-engine-monolithic'
import { Provider as StyletronProvider } from 'styletron-react'
import { BaseProvider } from 'baseui'
import './index.css'
import App from './App.jsx'
import { theme } from './theme.js'

const engine = new Styletron()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <StyletronProvider value={engine}>
      <BaseProvider theme={theme}>
        <App />
      </BaseProvider>
    </StyletronProvider>
  </StrictMode>,
)

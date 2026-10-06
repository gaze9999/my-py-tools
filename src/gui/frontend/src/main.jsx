import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import UI from './vendor/workbench-ui.mjs'
import './vendor/workbench-ui.css'
import './styles.css'

const root = document.getElementById('root')
root.classList.add('wb-workbench')
UI.setAppearance(root, { mode: 'dark', fontSize: 14 })
createRoot(root).render(<App />)

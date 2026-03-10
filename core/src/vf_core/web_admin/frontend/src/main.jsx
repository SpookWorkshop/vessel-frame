import { render } from 'preact';
import '@picocss/pico';
import './theme.css';
import { App } from './App';

render(<App />, document.getElementById('app'));

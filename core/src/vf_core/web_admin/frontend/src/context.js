import { createContext } from 'preact';
import { useContext } from 'preact/hooks';

export const AppContext = createContext({ onAuthError: () => {} });
export const useAppContext = () => useContext(AppContext);

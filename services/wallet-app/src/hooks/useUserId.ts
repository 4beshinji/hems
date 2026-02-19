import { useState, useCallback } from 'react';

const STORAGE_KEY = 'soms_user_id';

export function useUserId(): [number | null, (id: number) => void, () => void] {
  const [userId, setUserIdState] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? parseInt(stored, 10) : null;
  });

  const setUserId = useCallback((id: number) => {
    localStorage.setItem(STORAGE_KEY, String(id));
    setUserIdState(id);
  }, []);

  const clearUserId = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setUserIdState(null);
  }, []);

  return [userId, setUserId, clearUserId];
}

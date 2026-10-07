import { useEffect } from 'react';
import { Icon } from './Icon';

export function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 6000);
    return () => clearTimeout(t);
  }, [message, onDismiss]);
  return (
    <div className="toast" role="status">
      <Icon name="check" size={18} />
      <span>{message}</span>
      <button type="button" className="icon-btn icon-btn--light" onClick={onDismiss} aria-label="Dismiss message">
        <Icon name="x" size={16} />
      </button>
    </div>
  );
}

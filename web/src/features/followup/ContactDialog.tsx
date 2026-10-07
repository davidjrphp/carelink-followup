import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { ApiError, newId } from '../../api/http';
import type { ContactAttemptInput, FollowUpItem } from '../../api/types';
import { Icon } from '../../components/Icon';
import { formatDate, toLocalInputValue } from '../../lib/format';
import { useRecordContact } from './queries';

const NOTE_MAX = 500;

interface Props {
  item: FollowUpItem;
  onClose: () => void;
  onSaved: (item: FollowUpItem) => void;
}

type FieldErrors = Partial<Record<'contacted_at' | 'note', string>>;

/**
 * Modal dialog built on role="dialog" rather than <dialog>, which older clinic browsers lack.
 * Focus moves in on open, is trapped while open, and returns to the trigger on close (by the parent).
 */
export function ContactDialog({ item, onClose, onSaved }: Props) {
  const ids = { title: useId(), desc: useId(), when: useId(), note: useId() };
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstFieldRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [when, setWhen] = useState(() => toLocalInputValue(new Date()));
  const [note, setNote] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const mutation = useRecordContact();
  // One key per distinct submission: retrying the same content reuses it, so a retry after a
  // time-out can never record the attempt twice. Changing the content gets a fresh key.
  const keyRef = useRef<{ key: string; fingerprint: string } | null>(null);
  const name = `${item.first_name} ${item.last_name}`;

  useEffect(() => {
    firstFieldRef.current?.focus();
  }, []);

  function validate(): { ok: true; input: ContactAttemptInput } | { ok: false; errors: FieldErrors } {
    const next: FieldErrors = {};
    const date = when ? new Date(when) : null;
    if (!date || Number.isNaN(date.getTime())) {
      next.contacted_at = 'Enter the date and time you tried to contact the patient.';
    } else if (date.getTime() > Date.now() + 60_000) {
      next.contacted_at = 'The contact time cannot be in the future.';
    }
    if (note.length > NOTE_MAX) next.note = `Keep the note to ${NOTE_MAX} characters or fewer.`;
    setErrors(next);
    if (!date || Object.keys(next).length > 0) return { ok: false, errors: next };
    return { ok: true, input: { contacted_at: date.toISOString(), note: note.trim() || null } };
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (mutation.isPending) return;
    const result = validate();
    if (!result.ok) {
      // Move focus to the first field with a problem, so its error is read out.
      (result.errors.contacted_at ? firstFieldRef : noteRef).current?.focus();
      return;
    }
    const { input } = result;
    const fingerprint = JSON.stringify(input);
    if (!keyRef.current || keyRef.current.fingerprint !== fingerprint) {
      keyRef.current = { key: newId(), fingerprint };
    }
    mutation.mutate(
      { patientId: item.id, input, idempotencyKey: keyRef.current.key },
      {
        onSuccess: () => onSaved(item),
        onError: (err) => {
          // Map server-side field errors onto the fields they belong to.
          const fieldErrors: FieldErrors = {};
          for (const d of err.details) {
            if (d.field === 'contacted_at' || d.field === 'note') fieldErrors[d.field] = sentence(d.message);
          }
          setErrors(fieldErrors);
        },
      },
    );
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === 'Escape' && !mutation.isPending) {
      e.stopPropagation();
      onClose();
      return;
    }
    if (e.key !== 'Tab') return;
    const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [href]',
    );
    if (!focusables || focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  const serverError = mutation.error && Object.keys(errors).length === 0 ? mutation.error : null;

  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !mutation.isPending) onClose(); }}>
      <div
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={ids.title}
        aria-describedby={ids.desc}
        onKeyDown={onKeyDown}
      >
        <header className="modal__header">
          <div>
            <h2 id={ids.title} className="modal__title">Record contact attempt</h2>
            <p id={ids.desc} className="modal__subtitle">
              {name} · {item.patient_number} · missed {formatDate(item.missed_appointment_date)}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} disabled={mutation.isPending}
            aria-label="Close without saving">
            <Icon name="x" size={18} />
          </button>
        </header>

        <div className="modal__patient">
          <Icon name="phone" />
          {item.phone_number
            ? <span>Call <strong className="phone">{item.phone_number}</strong></span>
            : <span>No phone number recorded. Note how you tried to reach them.</span>}
        </div>

        <form noValidate onSubmit={submit} className="modal__form">
          {serverError && <ServerError error={serverError} />}

          <div className="field">
            <label htmlFor={ids.when}>Date and time of contact attempt</label>
            <input
              ref={firstFieldRef}
              id={ids.when}
              type="datetime-local"
              value={when}
              max={toLocalInputValue(new Date())}
              onChange={(e) => setWhen(e.target.value)}
              required
              aria-invalid={errors.contacted_at ? true : undefined}
              aria-describedby={errors.contacted_at ? `${ids.when}-error` : undefined}
            />
            {errors.contacted_at && (
              <p id={`${ids.when}-error`} className="field__error"><Icon name="alert" size={14} />{errors.contacted_at}</p>
            )}
          </div>

          <div className="field">
            <label htmlFor={ids.note}>Outcome <span className="field__optional">(optional)</span></label>
            <textarea
              ref={noteRef}
              id={ids.note}
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="For example: no answer, will try again tomorrow"
              aria-invalid={errors.note ? true : undefined}
              aria-describedby={`${ids.note}-hint${errors.note ? ` ${ids.note}-error` : ''}`}
            />
            <p id={`${ids.note}-hint`} className="field__hint field__hint--split">
              <span>Do not include diagnoses or test results.</span>
              <span aria-live="polite" className={note.length > NOTE_MAX ? 'over' : undefined}>
                {note.length}/{NOTE_MAX}
              </span>
            </p>
            {errors.note && (
              <p id={`${ids.note}-error`} className="field__error"><Icon name="alert" size={14} />{errors.note}</p>
            )}
          </div>

          <footer className="modal__actions">
            <button type="button" className="btn btn--ghost" onClick={onClose} disabled={mutation.isPending}>
              Cancel
            </button>
            <button type="submit" className="btn btn--primary" disabled={mutation.isPending}>
              {mutation.isPending
                ? <><span className="spinner spinner--light" aria-hidden="true" />Saving…</>
                : <><Icon name="check" />Save contact attempt</>}
            </button>
          </footer>
          <p className="sr-only" aria-live="assertive">{mutation.isPending ? 'Saving contact attempt' : ''}</p>
        </form>
      </div>
    </div>
  );
}

function ServerError({ error }: { error: ApiError }) {
  return (
    <div className="alert alert--danger" role="alert">
      <Icon name="alert" />
      <div>
        <p className="alert__title">Not saved</p>
        <p>
          {error.unreachable
            ? "Can't reach the server, so the contact attempt was not saved. Check the connection and press Save again; it will not be recorded twice."
            : error.message}
        </p>
        {error.correlationId && <p className="alert__ref">Reference: <code>{error.correlationId}</code></p>}
      </div>
    </div>
  );
}

function sentence(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1) + (s.endsWith('.') ? '' : '.');
}

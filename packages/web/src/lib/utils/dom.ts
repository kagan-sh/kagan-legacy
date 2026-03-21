export function isEditableTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return (
    element?.tagName === 'INPUT'
    || element?.tagName === 'TEXTAREA'
    || element?.tagName === 'SELECT'
    || Boolean(element?.isContentEditable)
  );
}

export function hasOpenOverlay(): boolean {
  return Boolean(
    document.querySelector(
      '[data-state="open"][role="dialog"], [data-state="open"][role="alertdialog"], [data-state="open"][role="listbox"]',
    ),
  );
}

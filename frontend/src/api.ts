let csrf = '';
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      ...options,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': csrf,
        ...options.headers,
      },
    });
  } catch {
    throw new Error('Нет соединения с сервером. Проверьте подключение и повторите.');
  }
  if (!response.ok) {
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/me')
      window.dispatchEvent(new Event('session-expired'));
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === 'string'
        ? body.detail
        : `Не удалось выполнить запрос (${response.status})`,
    );
  }
  return response.json();
}

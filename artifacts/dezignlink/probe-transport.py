# Engineering-only response metadata; installed into the already authorized
# capture session. Its original Session.send is restored by that session.
import hashlib as _ct_hashlib
_ct_output = r'C:\Users\asus\Documents\Python Project\CivTools\artifacts\dezignlink\runtime-transport.jsonl'
def _ct_send_transport(self, request, **kwargs):
    url = _ct_urlsplit(request.url)
    route = url.path.rstrip('/').rsplit('/', 1)[-1]
    if route not in _ct_routes:
        return _ct_original_send(self, request, **kwargs)
    record = {'route': route, 'host': url.hostname, 'timestamp': _ct_time.time()}
    try:
        response = _ct_original_send(self, request, **kwargs)
        record.update(status=response.status_code, content_type=response.headers.get('Content-Type'),
                      bytes=len(response.content), sha256=_ct_hashlib.sha256(response.content).hexdigest())
        try:
            record['response'] = _ct_clean(response.json())
        except ValueError:
            record['non_json'] = True
            record['known_error_markers'] = [s for s in ('Application Error', 'No such app',
                'Internal Server Error', 'Service Unavailable', 'Unauthorized', 'Forbidden')
                if s.lower() in response.text.lower()]
        return response
    except Exception as error:
        record['exception_type'] = type(error).__name__
        raise
    finally:
        with open(_ct_output, 'a', encoding='utf-8') as stream:
            stream.write(_ct_json.dumps(record) + '\n')
_ct_requests.sessions.Session.send = _ct_send_transport
with open(_ct_output, 'a', encoding='utf-8') as stream:
    stream.write(_ct_json.dumps({'session_type': type(s).__name__,
        'session_module': type(s).__module__}) + '\n')

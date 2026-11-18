def authenticated_fixture(client, csrf='test-token'):
    """Create a signed test session for already authenticated test cases."""
    sessions = client.application.extensions['dcc_updater_sessions']
    password_hash = sessions.password_path.read_text(encoding='utf-8').strip()
    with client.session_transaction() as state:
        state['sid'] = sessions.issue(password_hash)
        state['csrf_token'] = csrf

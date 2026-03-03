const status = document.getElementById('action-status');

async function postAction(url, body, btn, busyText, doneText, successMsg) {
  btn.disabled = true;
  btn.textContent = busyText;
  status.textContent = '';
  status.className = 'write-status';
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      btn.textContent = doneText;
      btn.disabled = false;
      status.textContent = data.error || 'Something went wrong.';
      status.className = 'write-status error';
      return;
    }
    btn.textContent = doneText;
    btn.disabled = false;
    status.textContent = successMsg(data);
    status.className = 'write-status success';
  } catch (e) {
    btn.textContent = doneText;
    btn.disabled = false;
    status.textContent = 'Error — check the console.';
    status.className = 'write-status error';
  }
}

async function writeTag(body) {
  const btn = document.getElementById('write-btn');
  const confirmBox = document.getElementById('write-confirm');
  btn.disabled = true;
  btn.textContent = 'Writing…';
  status.textContent = '';
  status.className = 'write-status';
  confirmBox.style.display = 'none';
  try {
    const resp = await fetch('/write-tag', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    btn.textContent = 'Write to Tag';
    btn.disabled = false;
    if (!resp.ok) {
      status.textContent = data.error || 'Something went wrong.';
      status.className = 'write-status error';
      return;
    }
    if (data.status === 'confirm') {
      document.getElementById('write-confirm-msg').textContent =
        'Tag already has: ' + data.existing_display;
      confirmBox.style.display = 'flex';
      return;
    }
    status.textContent = '✓ Written: ' + data.written;
    status.className = 'write-status success';
  } catch (e) {
    console.error('Write tag error:', e);
    btn.textContent = 'Write to Tag';
    btn.disabled = false;
    status.textContent = 'Network error — is the server running?';
    status.className = 'write-status error';
  }
}

document.getElementById('write-confirm-no').addEventListener('click', function() {
  document.getElementById('write-confirm').style.display = 'none';
});

// Evolution Engine — Landing Page Scripts

// ─── Mobile menu ───
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('.mobile-toggle');
  const links = document.querySelector('.nav-links');
  if (toggle && links) {
    toggle.addEventListener('click', () => {
      links.classList.toggle('open');
      toggle.textContent = links.classList.contains('open') ? '\u2715' : '\u2630';
    });
  }
});

// ─── Copy to clipboard ───
function copyToClipboard(text, el) {
  navigator.clipboard.writeText(text).then(() => {
    const tooltip = el.querySelector('.copy-tooltip');
    if (tooltip) {
      tooltip.classList.add('show');
      setTimeout(() => tooltip.classList.remove('show'), 1500);
    }
  });
}

// Attach to all code elements with data-copy
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-copy]').forEach(el => {
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => copyToClipboard(el.dataset.copy, el));
  });
});

// ─── Stripe checkout ───
function startCheckout() {
  fetch('/api/create-checkout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
    .then(res => res.json())
    .then(data => {
      if (data.url) {
        window.location.href = data.url;
      } else {
        alert('Could not start checkout. Please try again.');
      }
    })
    .catch(() => alert('Network error. Please try again.'));
}

// ─── Adapter request modal ───
function openAdapterModal() {
  document.getElementById('adapter-modal').classList.add('active');
}

function closeAdapterModal() {
  document.getElementById('adapter-modal').classList.remove('active');
  document.getElementById('adapter-form-message').className = 'form-message';
  document.getElementById('adapter-form-message').textContent = '';
}

function submitAdapterRequest(e) {
  e.preventDefault();
  const form = e.target;
  const data = {
    adapter_name: form.adapter_name.value.trim(),
    family: form.family.value,
    description: form.description.value.trim(),
    email: form.email.value.trim(),
    use_case: form.use_case.value.trim(),
  };

  if (!data.adapter_name || !data.family) {
    showFormMessage('Please fill in the adapter name and family.', 'error');
    return;
  }

  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = 'Submitting...';

  fetch('/api/adapter-request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
    .then(res => res.json())
    .then(result => {
      if (result.success) {
        showFormMessage('Request submitted! We\'ll track it as a GitHub issue.', 'success');
        form.reset();
      } else {
        showFormMessage(result.error || 'Something went wrong.', 'error');
      }
    })
    .catch(() => showFormMessage('Network error. Please try again.', 'error'))
    .finally(() => {
      btn.disabled = false;
      btn.textContent = 'Submit Request';
    });
}

function showFormMessage(text, type) {
  const el = document.getElementById('adapter-form-message');
  el.textContent = text;
  el.className = 'form-message ' + type;
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    closeAdapterModal();
  }
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeAdapterModal();
});

// ─── Scroll animations ───
document.addEventListener('DOMContentLoaded', () => {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.style.opacity = '1';
          entry.target.style.transform = 'translateY(0)';
        }
      });
    },
    { threshold: 0.1 }
  );

  document.querySelectorAll('.feature-card, .step, .pricing-card, .adapter-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
    observer.observe(el);
  });
});

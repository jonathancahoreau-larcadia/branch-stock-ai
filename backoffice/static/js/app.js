(function () {
  'use strict';

  /* ---- Modals ---- */
  var modalTriggers = document.querySelectorAll('[data-action="edit"], [data-action="password"]');

  function openModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('modal--open');
  }

  function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('modal--open');
  }

  /* Close modal on backdrop click */
  document.querySelectorAll('.modal__backdrop').forEach(function (backdrop) {
    backdrop.addEventListener('click', function () {
      var modal = this.closest('.modal');
      if (modal) modal.classList.remove('modal--open');
    });
  });

  /* Close modal on Escape key */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal--open').forEach(function (m) {
        m.classList.remove('modal--open');
      });
    }
  });

  /* ---- Edit user modal ---- */
  document.querySelectorAll('[data-action="edit"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var userId = this.getAttribute('data-user-id');
      var username = this.getAttribute('data-username');
      var branchId = this.getAttribute('data-branch-id');

      var form = document.getElementById('edit-user-form');
      if (!form) return;

      form.action = '/api/v1/users/' + userId;
      form.querySelector('#edit-username').value = username || '';
      form.querySelector('#edit-branch').value = branchId || '';
      openModal('edit-user-modal');
    });
  });

  /* ---- Change password modal ---- */
  document.querySelectorAll('[data-action="password"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var userId = this.getAttribute('data-user-id');
      var form = document.getElementById('password-form');
      if (!form) return;

      form.action = '/api/v1/users/' + userId + '/password';
      form.querySelector('#new-password').value = '';
      openModal('password-modal');
    });
  });

  /* ---- Active nav link ---- */
  var currentPath = window.location.pathname;
  document.querySelectorAll('.nav-link').forEach(function (link) {
    if (link.getAttribute('href') === currentPath) {
      link.classList.add('active');
    }
  });

})();
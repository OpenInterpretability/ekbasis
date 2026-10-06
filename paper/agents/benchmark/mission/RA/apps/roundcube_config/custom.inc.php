<?php
// WS-RA local test stack: IMAP/SMTP inside an internal Docker network, no TLS, no SMTP auth (Postfix trusts the network).
$config['imap_host'] = 'mailserver:143';
$config['smtp_host'] = 'mailserver:25';
$config['smtp_user'] = '';
$config['smtp_pass'] = '';
$config['product_name'] = 'Acme Webmail';
$config['support_url'] = '';
$config['enable_installer'] = false;
$config['draft_autosave'] = 0;
$config['mail_domain'] = 'acme.test';
$config['username_domain'] = 'acme.test';
$config['create_default_folders'] = true;
$config['skin'] = 'elastic';
$config['session_lifetime'] = 240;

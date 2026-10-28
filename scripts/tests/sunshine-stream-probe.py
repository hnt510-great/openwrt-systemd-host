#!/usr/bin/env python3
"""Pair with an isolated Sunshine test instance and prepare a headless stream.

Requires requests and cryptography. Never point this at a user's pairing state:
use a separate Sunshine configuration, test credentials, certificate and ports.
HTTPS certificate verification uses the supplied server certificate as a trust
anchor; its IP/name is allowed to differ for an SSH-forwarded guest endpoint.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import time
import urllib.parse
import uuid
import xml.etree.ElementTree as ET

import requests
from requests.adapters import HTTPAdapter
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import NameOID


class PinnedAdapter(HTTPAdapter):
    def __init__(self, context):
        self.context = context
        super().__init__()

    def init_poolmanager(self, *args, **kwargs):
        kwargs.update(ssl_context=self.context, assert_hostname=False)
        return super().init_poolmanager(*args, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=48989)
    parser.add_argument('--server-cert', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True, help='JSON with test username/password')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--width', type=int, default=1920)
    parser.add_argument('--height', type=int, default=1080)
    parser.add_argument('--fps', type=int, default=60)
    parser.add_argument('--cancel', action='store_true')
    parser.add_argument('--require-paired', action='store_true',
                        help='Fail instead of pairing again; use for persistence acceptance')
    args = parser.parse_args()
    os.umask(0o077)
    args.state.mkdir(parents=True, exist_ok=True, mode=0o700)
    key_path, cert_path = args.state / 'key.pem', args.state / 'cert.pem'
    if not key_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'OpenWrt capture validation')])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=7)).sign(key, hashes.SHA256()))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key = serialization.load_pem_private_key(key_path.read_bytes(), None)
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    server_cert = x509.load_pem_x509_certificate(args.server_cert.read_bytes())
    client_id = hashlib.sha256(cert_path.read_bytes()).hexdigest()[:16]
    params = dict(uniqueid=client_id, uuid=uuid.uuid4().hex, devicename='OpenWrt capture validation', updateState=1)
    context = ssl.create_default_context(cafile=str(args.server_cert))
    context.check_hostname = False
    context.load_cert_chain(cert_path, key_path)
    session = requests.Session()
    session.trust_env = False
    session.verify = str(args.server_cert)
    session.mount('https://', PinnedAdapter(context))
    credentials = json.loads(args.credentials.read_text())
    auth = (credentials['username'], credentials['password'])
    http = f'http://{args.host}:{args.port}'
    https = f'https://{args.host}:{args.port - 5}'
    web = f'https://{args.host}:{args.port + 1}'

    def xml(base, path, **values):
        for attempt in range(2):
            try:
                response = session.get(base + path, params=dict(params, **values), timeout=30)
                break
            except requests.ConnectionError:
                # A server may close a reused HTTPS connection between reads.
                # Only repeat queries: launch, resume and pairing change state.
                if attempt or path not in ('/serverinfo', '/applist'):
                    raise
        response.raise_for_status()
        tree = ET.fromstring(response.content)
        if tree.get('status_code') == '401':
            raise PermissionError('GameStream client has not been paired')
        if tree.get('status_code') != '200':
            raise RuntimeError(ET.tostring(tree).decode())
        return tree

    def web_get(path):
        response = session.get(web + path, auth=auth, timeout=5)
        response.raise_for_status()
        return response.json()

    info = xml(http, '/serverinfo')
    try:
        paired = xml(https, '/serverinfo').findtext('PairStatus') == '1'
    except (requests.HTTPError, PermissionError):
        paired = False
    if args.require_paired and not paired:
        raise PermissionError('The previously paired test client is no longer trusted')
    if not paired:
        pin, salt = f'{secrets.randbelow(10000):04d}', os.urandom(16)
        aes_key = hashlib.sha256(salt + pin.encode()).digest()[:16]

        def crypt(data, encrypt=True):
            cipher = Cipher(algorithms.AES(aes_key), modes.ECB())
            operation = cipher.encryptor() if encrypt else cipher.decryptor()
            return operation.update(data) + operation.finalize()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            pending = pool.submit(xml, http, '/pair', phrase='getservercert', salt=salt.hex(), clientcert=cert_path.read_bytes().hex())
            pairings = []
            for _ in range(40):
                pairings = web_get('/api/pin')['pairings']
                if pairings:
                    break
                time.sleep(.1)
            if len(pairings) != 1:
                raise RuntimeError('Expected exactly one pending pairing on the isolated test instance')
            token = web_get('/api/csrf-token')['csrf_token']
            approval = pool.submit(session.post, web + '/api/pin', auth=auth,
                                    headers={'X-CSRF-Token': token},
                                    json=dict(pairing_id=pairings[0]['id'], pin=pin, name='OpenWrt capture validation'), timeout=30)
            paired_response = pending.result()
            received = x509.load_pem_x509_certificate(bytes.fromhex(paired_response.findtext('plaincert')))
            if received.fingerprint(hashes.SHA256()) != server_cert.fingerprint(hashes.SHA256()):
                raise RuntimeError('Pairing certificate differs from the supplied server certificate')
            challenge = os.urandom(16)
            response = xml(http, '/pair', clientchallenge=crypt(challenge).hex())
            decoded = crypt(bytes.fromhex(response.findtext('challengeresponse')), False)
            secret = os.urandom(16)
            answer = hashlib.sha256(decoded[32:48] + cert.signature + secret).digest()
            response = xml(http, '/pair', serverchallengeresp=crypt(answer).hex())
            server_secret = bytes.fromhex(response.findtext('pairingsecret'))
            received.public_key().verify(server_secret[16:], server_secret[:16], padding.PKCS1v15(), hashes.SHA256())
            if hashlib.sha256(challenge + received.signature + server_secret[:16]).digest() != decoded[:32]:
                raise RuntimeError('Server challenge verification failed')
            signed_secret = secret + key.sign(secret, padding.PKCS1v15(), hashes.SHA256())
            xml(http, '/pair', clientpairingsecret=signed_secret.hex())
            xml(https, '/pair', phrase='pairchallenge')
            approval.result().raise_for_status()
    if args.cancel:
        xml(https, '/cancel')
        return
    info = xml(https, '/serverinfo')
    app = xml(https, '/applist').find('App')
    aes, key_id = os.urandom(16).hex(), secrets.randbits(31)
    result = xml(https, '/resume' if info.findtext('currentgame') not in ('0', None) else '/launch',
                 appid=app.findtext('ID'), mode=f'{args.width}x{args.height}x{args.fps}',
                 additionalStates=1, sops=0, rikey=aes, rikeyid=key_id,
                 localAudioPlayMode=1, surroundAudioInfo=196610,
                 remoteControllersBitmap=0, gcmap=0)
    url = result.findtext('sessionUrl0')
    if not url:
        raise RuntimeError('No RTSP session URL returned')
    args.manifest.write_text(json.dumps([args.host, info.findtext('appversion'),
                                        info.findtext('GfeVersion') or '3.23.0.74', url, aes, str(key_id)]))
    print('Prepared authenticated H.264 stream; private manifest:', args.manifest)


if __name__ == '__main__':
    main()

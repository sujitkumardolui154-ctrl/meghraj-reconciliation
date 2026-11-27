#!/usr/bin/env python3
"""R31.11.4J — TRUE TLS socket/mTLS checks with SYNTHETIC disposable certs.

This is a loopback-only acceptance rehearsal, NOT external HTTP/HTTPS, not
live Caddy, not a real trusted CA and not a substitute for real mTLS E2E.

Runs no shell commands and never touches production or PostgreSQL. Test keys
are generated under a unique temporary 0700 directory, files mode 0600,
removed after the test. Every listener binds ONLY to 127.0.0.1.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import socket
import ssl
import stat
from tempfile import TemporaryDirectory
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption

HOST = "127.0.0.1"
SERVER_NAME = "qa-r3114j.invalid"
MAX_SECONDS = 5


class SyntheticBlocked(RuntimeError):
    pass


def require(ok, msg):
    if not ok:
        raise SyntheticBlocked(msg)


def new_ca(common_name):
    key=ec.generate_private_key(ec.SECP256R1())
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,common_name)])
    now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder()
          .subject_name(name).issuer_name(name)
          .public_key(key.public_key())
          .serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(days=1))
          .not_valid_after(now+timedelta(days=2))
          .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
          .add_extension(x509.KeyUsage(
              digital_signature=True,key_encipherment=False,content_commitment=False,
              data_encipherment=False,key_agreement=False,key_cert_sign=True,
              crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
          .sign(key,hashes.SHA256()))
    return key,cert


def new_leaf(common_name, issuer_key,issuer_cert, *, server=False, expired=False):
    key=ec.generate_private_key(ec.SECP256R1())
    now=datetime.now(timezone.utc)
    before=now-timedelta(days=3) if expired else now-timedelta(minutes=5)
    after=now-timedelta(days=1) if expired else now+timedelta(days=1)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,common_name)])
    usages=[ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]
    builder=(x509.CertificateBuilder()
          .subject_name(subject).issuer_name(issuer_cert.subject)
          .public_key(key.public_key())
          .serial_number(x509.random_serial_number())
          .not_valid_before(before).not_valid_after(after)
          .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
          .add_extension(x509.KeyUsage(
             digital_signature=True,key_encipherment=False,content_commitment=False,
             data_encipherment=False,key_agreement=False,key_cert_sign=False,
             crl_sign=False,encipher_only=False,decipher_only=False),critical=True)
          .add_extension(x509.ExtendedKeyUsage(usages),critical=False))
    if server:
        builder=builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(SERVER_NAME)]),
            critical=False)
    return key,builder.sign(issuer_key,hashes.SHA256())


def secure_write(path, data):
    flags=os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"wb") as output:
            output.write(data)
    finally:
        pass
    require(stat.S_IMODE(path.stat().st_mode)==0o600,"SYNTHETIC_KEY_MODE_CHANGED")


def pem_pair(dir_path, name, pair):
    key,cert=pair
    crt=dir_path/(name+".crt")
    priv=dir_path/(name+".key")
    secure_write(crt,cert.public_bytes(Encoding.PEM))
    secure_write(priv,key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
    return crt,priv


def tls_server_ctx(server_pair, ca_path):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.verify_mode=ssl.CERT_REQUIRED
    ctx.load_cert_chain(str(server_pair[0]),str(server_pair[1]))
    ctx.load_verify_locations(cafile=str(ca_path))
    return ctx


def tls_client_ctx(trust_server_ca, cert_pair=None):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.verify_mode=ssl.CERT_REQUIRED
    ctx.check_hostname=True
    ctx.load_verify_locations(cafile=str(trust_server_ca))
    if cert_pair:
        ctx.load_cert_chain(str(cert_pair[0]),str(cert_pair[1]))
    return ctx


def exchange(server_ctx, client_ctx, *, sni=SERVER_NAME):
    """One bounded, real TLS over localhost. Returns (HTTP_200, server_mTLS).

    A negative case may fail in TLS or immediately on authenticated I/O;
    it must NEVER receive an HTTP 200 response from this guarded server.
    """
    confirmed={"client":False,"server":False}
    errors=[]
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind((HOST,0))
        listener.listen(1)
        listener.settimeout(MAX_SECONDS)
        port=listener.getsockname()[1]

        def serve_once():
            try:
                raw, _=listener.accept()
                raw.settimeout(MAX_SECONDS)
                with raw:
                    with server_ctx.wrap_socket(raw,server_side=True) as secure:
                        # SSLContext with CERT_REQUIRED verifies the CA
                        # chain before handing the application a socket.
                        confirmed["server"]=bool(secure.getpeercert())
                        if not confirmed["server"]:
                            return
                        request=secure.recv(256)
                        if request.startswith(b"GET /qa-only HTTP/1.1\r\n"):
                            secure.sendall(
                                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                                b"Connection: close\r\n\r\nOK")
            except (ssl.SSLError,ConnectionError,TimeoutError,OSError):
                return
            except Exception:
                errors.append("SERVER_UNEXPECTED_ERROR")
        thread=threading.Thread(target=serve_once,daemon=True)
        thread.start()
        try:
            with socket.create_connection((HOST,port),timeout=MAX_SECONDS) as raw:
                raw.settimeout(MAX_SECONDS)
                with client_ctx.wrap_socket(raw,server_hostname=sni) as client:
                    client.sendall(b"GET /qa-only HTTP/1.1\r\n"
                                   b"Host: qa-r3114j.invalid\r\nConnection:close\r\n\r\n")
                    response=client.recv(512)
                    confirmed["client"]=response.startswith(b"HTTP/1.1 200 OK")
        except (ssl.SSLError,ConnectionError,TimeoutError,OSError):
            pass
        finally:
            thread.join(timeout=MAX_SECONDS+1)
        require(not thread.is_alive() and not errors,"SYNTHETIC_TLS_SOCKET_TEST_INCOMPLETE")
    return confirmed["client"],confirmed["server"]


def run_synthetic():
    with TemporaryDirectory(prefix="r3114j-synthetic-") as dir_string:
        folder=Path(dir_string)
        require(stat.S_IMODE(folder.stat().st_mode)==0o700,
                "SYNTHETIC_CERT_DIR_NOT_PRIVATE")
        ca=new_ca("R3114J disposable CI CA")
        other=new_ca("R3114J untrusted CI CA")
        ca_cert=folder/"ca.crt"
        other_cert=folder/"other.crt"
        secure_write(ca_cert,ca[1].public_bytes(Encoding.PEM))
        secure_write(other_cert,other[1].public_bytes(Encoding.PEM))
        server=pem_pair(folder,"server",new_leaf(
            SERVER_NAME,ca[0],ca[1],server=True))
        valid=pem_pair(folder,"client-valid",new_leaf(
            "qa-valid-client",ca[0],ca[1]))
        wrong=pem_pair(folder,"client-wrong-ca",new_leaf(
            "qa-wrong-ca-client",other[0],other[1]))
        expired=pem_pair(folder,"client-expired",new_leaf(
            "qa-expired-client",ca[0],ca[1],expired=True))

        server_ctx=tls_server_ctx(server,ca_cert)
        accepted=tls_client_ctx(ca_cert,valid)
        require(exchange(server_ctx,accepted)==(True,True),
                "SYNTHETIC_VALID_CLIENT_NOT_ACCEPTED")
        print("DB_R31_11_4J_VALID_CLIENT_CERT=PASS_TLS12_PLUS_LOOPBACK",flush=True)

        no_cert=tls_client_ctx(ca_cert)
        require(exchange(server_ctx,no_cert)[0] is False,
                "SYNTHETIC_NO_CLIENT_CERT_ACCEPTED")
        print("DB_R31_11_4J_NO_CLIENT_CERT=DENIED_PASS",flush=True)

        unknown_ca=tls_client_ctx(ca_cert,wrong)
        require(exchange(server_ctx,unknown_ca)[0] is False,
                "SYNTHETIC_WRONG_CLIENT_CA_ACCEPTED")
        print("DB_R31_11_4J_WRONG_CLIENT_CA=DENIED_PASS",flush=True)

        expired_client=tls_client_ctx(ca_cert,expired)
        require(exchange(server_ctx,expired_client)[0] is False,
                "SYNTHETIC_EXPIRED_CLIENT_CERT_ACCEPTED")
        print("DB_R31_11_4J_EXPIRED_CLIENT_CERT=DENIED_PASS",flush=True)

        wrong_sni=tls_client_ctx(ca_cert,valid)
        require(exchange(server_ctx,wrong_sni,sni="different.invalid")[0] is False,
                "SYNTHETIC_WRONG_SERVER_NAME_ACCEPTED")
        print("DB_R31_11_4J_WRONG_SERVER_NAME=DENIED_PASS",flush=True)

        wrong_server_ca=tls_client_ctx(other_cert,valid)
        require(exchange(server_ctx,wrong_server_ca)[0] is False,
                "SYNTHETIC_WRONG_SERVER_CA_ACCEPTED")
        print("DB_R31_11_4J_WRONG_SERVER_CA=DENIED_PASS",flush=True)

    print("DB_R31_11_4J_SYNTHETIC_KEYS=DISCARDED_TEMP_DIRECTORY",flush=True)
    print("DB_R31_11_4J_LOOPBACK_MTLS=PASS_SYNTHETIC_ONLY",flush=True)


if __name__=="__main__":
    try:
        run_synthetic()
    except Exception:
        print("STOP=DB_R31_11_4J_SYNTHETIC_MTLS_QA_FAILED",flush=True)
        raise SystemExit(2)
    finally:
        print("DB_R31_11_4J_EXTERNAL_MTLS_HTTPS=NOT_TESTED",flush=True)
        print("DB_R31_11_4J_FINANCIAL_APPLY=LOCKED",flush=True)
        print("DB_R31_11_4J_PRODUCTION_RELEASE=BLOCKED",flush=True)

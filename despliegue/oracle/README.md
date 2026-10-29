# Despliegue de DEBUPA en Oracle Cloud Always Free

Esta guía prepara una VM Ubuntu ARM64 de Oracle Cloud para ejecutar DEBUPA con un
solo proceso Uvicorn, un navegador Playwright activo y un segundo opcional, con PostgreSQL en Supabase.

## Decisiones de producción

- La VM debe tener recursos suficientes para Chromium. En Always Free se recomienda
  `VM.Standard.A1.Flex` con 2 OCPU y 12 GB de memoria si hay capacidad disponible.
- No uses `--reload` ni varios workers. La cola y el navegador SGVA son únicos en el
  proceso de la aplicación.
- El disco local solo aloja el código y los navegadores. Los datos de DEBUPA van a
  PostgreSQL y los comprobantes se conservan cifrados en la base activa.
- Nginx termina HTTPS y reenvía a FastAPI en `127.0.0.1:8000`.

## Orden de instalación en la VM

Conéctate por SSH como `ubuntu` y ejecuta:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx python3-venv python3-pip ca-certificates curl ufw
sudo adduser --system --group --home /opt/debupa debupa
sudo mkdir -p /etc/debupa
sudo chown -R debupa:debupa /opt/debupa
```

Clona el repositorio:

```bash
sudo -u debupa git clone https://github.com/Juanfepm/sena-oportunidades.git /opt/debupa
cd /opt/debupa
sudo -u debupa python3 -m venv .venv
sudo -u debupa .venv/bin/python -m pip install --upgrade pip
sudo -u debupa .venv/bin/pip install -r backend/requirements-postgresql.txt
sudo -u debupa .venv/bin/python -m playwright install --with-deps chromium
```

## Variables privadas

Crea el archivo protegido. No lo subas a GitHub:

```bash
sudo nano /etc/debupa/debupa.env
sudo chown root:debupa /etc/debupa/debupa.env
sudo chmod 640 /etc/debupa/debupa.env
```

Contenido mínimo:

```text
DEBUPA_ENTORNO=produccion
DEBUPA_SGVA_ACTIVO=true
DEBUPA_ORIGEN_PUBLICO=https://TU_DOMINIO
DEBUPA_BASE_DATOS=postgresql+psycopg://USUARIO:CONTRASEÑA@HOST:5432/postgres?sslmode=verify-full
DEBUPA_SECRETO_SESION=SECRETO_ALEATORIO_DE_AL_MENOS_32_CARACTERES
DEBUPA_CLAVE_CIFRADO=CLAVE_FERNET
DEBUPA_CORREO_ADMIN=debupawebapp@gmail.com
GOOGLE_CLIENTE_ID=CLIENTE_DE_GOOGLE
GOOGLE_CLIENTE_SECRETO=SECRETO_DE_GOOGLE
GOOGLE_URI_REDIRECCION=https://TU_DOMINIO/api/v1/autenticacion/google/callback
GOOGLE_URL_INICIO=/#inicio
GEMINI_API_KEY=CLAVE_DE_GEMINI
PGSSLROOTCERT=/etc/ssl/certs/supabase-ca.crt
```

Descarga el certificado CA de Supabase y cópialo a la ruta indicada. La contraseña
de PostgreSQL debe estar codificada para URL si contiene caracteres especiales.

## Migraciones y servicio

```bash
cd /opt/debupa
sudo install -o root -g root -m 644 despliegue/oracle/debupa.service /etc/systemd/system/debupa.service
sudo install -o root -g root -m 644 despliegue/oracle/debupa-migrate.service /etc/systemd/system/debupa-migrate.service
sudo systemctl daemon-reload
sudo systemctl start debupa-migrate
sudo systemctl enable --now debupa
sudo systemctl status debupa --no-pager
```

La migración usa el mismo archivo protegido de systemd y no necesita pegar la cadena
de PostgreSQL en la terminal.

## Nginx y HTTPS

Antes de activar HTTPS, apunta el registro DNS `A` de tu dominio a la IP pública
reservada de la VM. Después:

```bash
sudo sed "s/TU_DOMINIO/tu-dominio.com/g" \
  /opt/debupa/despliegue/oracle/nginx-debupa.conf \
  | sudo tee /etc/nginx/sites-available/debupa.conf >/dev/null
sudo ln -s /etc/nginx/sites-available/debupa.conf /etc/nginx/sites-enabled/debupa.conf
sudo nginx -t
sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tu-dominio.com
```

Luego cambia `DEBUPA_ORIGEN_PUBLICO` y `GOOGLE_URI_REDIRECCION` para usar el dominio
HTTPS y reinicia:

```bash
sudo systemctl restart debupa
```

## Firewall

En Oracle Cloud agrega reglas de entrada TCP para 80 y 443 en la Security List o
Network Security Group de la subred. Conserva TCP 22 solo desde tu IP si es posible.

En la VM:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

No abras el puerto 8000 públicamente: Nginx es el único servicio que debe exponerlo.

## Actualizar DEBUPA

```bash
cd /opt/debupa
sudo systemctl stop debupa
sudo -u debupa git pull origin main
sudo -u debupa .venv/bin/pip install -r backend/requirements-postgresql.txt
sudo systemctl start debupa-migrate
sudo systemctl start debupa
sudo journalctl -u debupa -n 100 --no-pager
```

## Comprobaciones

Para habilitar el segundo navegador desde la VM después de la migración, usa
el entorno del servicio y la misma base de datos:

```bash
sudo systemd-run --wait --collect --pipe \
  -p User=debupa -p WorkingDirectory=/opt/debupa \
  -p EnvironmentFile=/etc/debupa/debupa.env \
  /opt/debupa/.venv/bin/python -m backend.aplicacion.consola_navegadores activar
```

Sustituye `activar` por `estado` o `desactivar` según necesites. El cambio se
detecta sin reiniciar el servidor. Deja un solo proceso Uvicorn para que las
credenciales en memoria y la cola se compartan entre los dos navegadores.

```bash
curl -I https://TU_DOMINIO/
curl -I https://TU_DOMINIO/docs
sudo systemctl is-active debupa
sudo nginx -t
```

Después prueba Google OAuth, Gmail, una campaña de demostración, una consulta SGVA,
dos campañas concurrentes, el envío de prueba y el flujo Premium.


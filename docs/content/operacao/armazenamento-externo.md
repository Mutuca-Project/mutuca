# Armazenamento externo como object storage

O Mutuca roda em hardware de redação — um notebook ou servidor compacto com, tipicamente, 512 GB a 1 TB de armazenamento interno. Investigações com dados da Receita Federal, TSE ou CGU facilmente ultrapassam centenas de gigabytes. Usar um HD externo como backend do MinIO é a solução natural para esse problema.

Esta página explica como essa integração funciona, como configurá-la de forma estável e como resolver os problemas mais comuns.

---

## Como o MinIO usa o HD externo

O MinIO armazena todos os seus dados num diretório chamado `/data` dentro do container. Por padrão, esse diretório é um volume Docker gerenciado internamente — os dados ficam no disco interno do servidor.

O arquivo `docker-compose.hd.yml` substitui esse volume por um **bind mount** para um diretório no HD externo:

```yaml
# docker-compose.hd.yml
services:
  minio:
    volumes:
      - ${MINIO_DATA_PATH}:/data
```

Quando o stack sobe com `make up-hd`, o MinIO passa a ler e gravar em `MINIO_DATA_PATH` no HD externo. Tudo que é escrito nos buckets (`bronze/`, `silver/`, `gold/`, `warehouse/`) vai para o HD. Para o MinIO e para todos os serviços que consomem dados via S3, nada muda — a diferença é totalmente transparente.

---

## Configuração inicial

### 1. Definir `MINIO_DATA_PATH` no `.env`

```bash
MINIO_DATA_PATH="/mnt/expansion_hd/DATALAKE/MINIO"
```

O diretório precisa existir antes do primeiro `make up-hd`:

```bash
mkdir -p /mnt/expansion_hd/DATALAKE/MINIO
```

### 2. Subir o stack com HD

```bash
make up-hd
```

Isso equivale a:

```bash
docker compose -f docker-compose.yml -f docker-compose.hd.yml up -d
```

### 3. Verificar que o MinIO está usando o HD

```bash
docker inspect lakehouse-minio | grep Source
```

O campo `Source` deve apontar para o caminho do HD. Se estiver apontando para um caminho diferente, o bind mount não está correto.

---

## Configurar um ponto de montagem fixo (recomendado)

Por padrão, o Linux monta HDs externos com nomes baseados no label do volume (`/media/usuario/NomeDoHD`). Isso causa um problema sério com o Docker: se o HD for desconectado enquanto o Docker estiver rodando com um bind mount ativo, o Linux não consegue reusar o mesmo ponto de montagem quando o HD é reconectado — e incrementa um número no nome (`NomeDoHD1`, `NomeDoHD2`, `NomeDoHD3`...).

O resultado é que o `MINIO_DATA_PATH` no `.env` fica desatualizado, o MinIO abre apontando para um diretório vazio, e dados escritos nessa sessão vão para o lugar errado.

A solução é montar o HD por UUID com um caminho fixo definido no `/etc/fstab`.

**Passo 1 — Identificar o UUID e o tipo de sistema de arquivos:**

```bash
lsblk -o NAME,FSTYPE,LABEL,UUID | grep -i <nome-do-label>
```

**Passo 2 — Identificar o UID do usuário:**

```bash
id $USER
```

**Passo 3 — Criar o ponto de montagem fixo:**

```bash
sudo mkdir -p /mnt/expansion_hd
```

**Passo 4 — Adicionar ao `/etc/fstab`:**

Para HD exFAT (caso mais comum em HDs de consumo):

```
UUID=XXXX-XXXX  /mnt/expansion_hd  exfat  uid=1000,gid=1000,umask=022,nofail,x-gvfs-show  0  0
```

Para HD NTFS:

```
UUID=XXXXXXXXXXXXXXXX  /mnt/expansion_hd  ntfs-3g  uid=1000,gid=1000,umask=022,nofail,x-gvfs-show  0  0
```

As opções importantes:

| Opção | Função |
|---|---|
| `uid=1000,gid=1000` | Garante que o usuário tem permissão de escrita sem `sudo` |
| `nofail` | O sistema não trava no boot se o HD não estiver conectado |
| `x-gvfs-show` | Mostra o HD na barra lateral do gerenciador de arquivos |

**Passo 5 — Testar:**

```bash
sudo mount /mnt/expansion_hd
ls /mnt/expansion_hd
```

**Passo 6 — Atualizar o `.env`:**

```bash
MINIO_DATA_PATH="/mnt/expansion_hd/DATALAKE/MINIO"
RFB_CNPJ_HD_PATH=/mnt/expansion_hd/DATALAKE/RAW/receita_federal_cnpj
```

---

## Problemas comuns e soluções

### A porta 9000 já está em uso ao tentar subir o stack

**Sintoma:**

```
failed to bind host port 0.0.0.0:9000/tcp: address already in use
```

**Diagnóstico:**

```bash
sudo lsof -i :9000
```

Se o processo for `python` (geralmente Jupyter), encerre-o:

```bash
kill <PID>
```

Se o processo for `lakehouse-minio` de uma instância anterior do Docker que ficou travada:

```bash
make down && make up-hd
```

**Atenção:** se você matar o processo e tentar `make up-hd` sem antes derrubar o stack com `make down`, o Docker pode subir o container MinIO sem os mapeamentos de porta (sem erro aparente, mas o MinIO fica inacessível).

---

### O caminho do HD está incrementando (`Expansion` → `Expansion1` → `Expansion2`)

**Causa:** o automontador do Linux (udisks2) não consegue reusar um ponto de montagem que o Docker está segurando com um bind mount ativo. Cada nova montagem cria um diretório com número incrementado.

**Como confirmar:**

```bash
ls /media/$USER/
docker inspect lakehouse-minio | grep Source
```

Se `Source` aponta para `Expansion1` mas o HD está em `Expansion2`, o MinIO está escrevendo num diretório que não é o HD.

**Solução definitiva:** configurar o ponto de montagem fixo via `fstab` conforme descrito acima. Isso elimina o problema permanentemente porque o HD passa a ser montado pelo sistema, não pelo automontador do desktop.

**Solução imediata** (sem fstab):

```bash
make down

# Editar .env e corrigir o número no MINIO_DATA_PATH
nano .env  # ou seu editor preferido

make up-hd
docker inspect lakehouse-minio | grep Source  # confirmar
```

Depois limpar os diretórios órfãos (apenas com o Docker parado):

```bash
sudo rmdir /media/$USER/Expansion
sudo rmdir /media/$USER/Expansion1
```

Use `rmdir` — falha se o diretório não estiver vazio, protegendo contra remoção acidental de dados.

---

### A pasta do HD aparece vazia

**Causa mais comum:** o HD não está montado. O ponto de montagem é um diretório vazio quando nenhum dispositivo está montado nele.

**Diagnóstico:**

```bash
mount | grep expansion_hd
```

Se não aparecer nada, o HD não está montado. Remonte:

```bash
sudo mount /mnt/expansion_hd
ls /mnt/expansion_hd
```

Se o `ls` mostrar os arquivos, está tudo certo. Os dados nunca sumiram — o diretório simplesmente estava desmontado.

**Por que isso acontece?** O `nofail` no fstab garante que o sistema não trava no boot se o HD não estiver conectado — mas também significa que o boot continua silenciosamente sem montar o HD se ele não estiver presente. Conecte o HD e monte manualmente, ou reinicie com o HD conectado.

---

### O ícone do HD não aparece no gerenciador de arquivos

**Causa:** HDs configurados via fstab são gerenciados pelo sistema operacional, não pelo automontador do desktop (udisks2). O GNOME só exibe dispositivos gerenciados pelo udisks2 na barra lateral.

**Solução 1 — `x-gvfs-show` no fstab (recomendado):**

Adicione `x-gvfs-show` às opções no fstab. Isso instrui o GNOME a exibir o ponto de montagem na barra lateral como se fosse um dispositivo gerenciado.

```
UUID=XXXX-XXXX  /mnt/expansion_hd  exfat  uid=1000,gid=1000,umask=022,nofail,x-gvfs-show  0  0
```

Para aplicar sem reiniciar:

```bash
sudo umount /mnt/expansion_hd && sudo mount /mnt/expansion_hd
```

**Solução 2 — Favorito no Nautilus:**

Abra o gerenciador de arquivos, navegue até `/mnt/expansion_hd` e pressione `Ctrl+D` para adicionar como favorito na barra lateral.

---

## Verificação rápida do estado do storage

Para confirmar que tudo está funcionando corretamente antes de iniciar uma sessão de trabalho:

```bash
# HD montado?
mount | grep expansion_hd

# MinIO apontando para o caminho certo?
docker inspect lakehouse-minio 2>/dev/null | grep '"Source"'

# Buckets acessíveis?
ls /mnt/expansion_hd/DATALAKE/MINIO/
```

Os três comandos devem retornar resultados não-vazios. Se qualquer um falhar, consulte a seção de problemas acima antes de iniciar uma ingestão.

# Service Desk

Sistema web para abertura, distribuição e acompanhamento de chamados internos, construído com Django, Django REST Framework e PostgreSQL. A interface é responsiva e oferece visões diferentes para solicitantes, agentes e administradores.

## Recursos entregues

- Login do Django com bloqueio temporário após cinco tentativas malsucedidas por conta e endereço de origem.
- Perfis `Administrador`, `Agente de suporte` e `Solicitante`.
- Abertura, listagem, busca e filtros por status, prioridade e categoria.
- Atribuição, mudança de categoria/prioridade, transições controladas de status, resolução, encerramento e reabertura.
- Comentários públicos e notas internas, com visibilidade protegida.
- Histórico de auditoria para alterações, comentários e transições do chamado.
- Indicadores de fila, prioridade e tempo médio de resolução calculados a partir dos dados reais.
- API REST paginada, com busca, filtros, ordenação, documentação Swagger e as mesmas regras de visibilidade da interface.
- Autenticação da API por tokens revogáveis com validade de 30 dias e limitação de requisições.
- Indicadores reais de primeira resposta, resolução e chamados fora do SLA configurável.
- Testes com pytest/pytest-django, Docker Compose e integração contínua no GitHub Actions.

## Arquitetura

```
config/             Configuração Django, URLs e WSGI
tickets/            Domínio de chamados, regras de negócio, páginas e API
templates/          Templates renderizados no servidor
static/css/          Design system da aplicação
.github/workflows/  Pipeline de integração contínua
```

As regras que mudam o ciclo de vida ficam em `tickets/services.py`, não nos templates ou serializers. Isso evita que a API contorne as regras aplicadas pela interface.

## Perfis e regras de negócio

| Ação | Solicitante | Agente | Administrador |
| --- | --- | --- | --- |
| Abrir e visualizar próprios chamados | Sim | Sim | Sim |
| Visualizar todos os chamados | Não | Sim | Sim |
| Comentar | Somente comentário público em chamados próprios | Sim | Sim |
| Atribuir, alterar prioridade/categoria/status | Não | Sim | Sim |
| Gerenciar usuários e cadastros de apoio | Não | Não | Sim, pelo Django Admin |
| Excluir chamado | Não | Não | Não; remoção bloqueada para preservar a auditoria |

Transições permitidas: **Aberto → Em andamento/Encerrado**, **Em andamento → Aguardando solicitante/Resolvido/Encerrado**, **Aguardando solicitante → Em andamento/Resolvido/Encerrado**, **Resolvido → Encerrado/Em andamento** e **Encerrado → Em andamento** (reabertura). Atribuições exigem um agente ou administrador ativo.

Usuários inativos não conseguem autenticar-se; responsáveis inativos são recusados pela validação do modelo. O perfil Administrador recebe acesso ao Django Admin e às permissões de gerenciamento do sistema. Um Administrador pode classificar outras contas como Agente ou Solicitante. A criação de outro Administrador e o gerenciamento de superusuários exigem uma conta de superusuário criada pelo comando `createsuperuser`.

Alterações relevantes registram responsável, data e valores anterior/posterior. Edições e exclusões de comentários também geram auditoria. Os registros não podem ser editados ou excluídos pelo painel ou pela API. Chamados com histórico não podem ser removidos; usuários com chamados ou registros associados também ficam protegidos contra exclusão.

## Executar com Docker

Pré-requisito: Docker com Docker Compose.

Linux e macOS:

```bash
cp .env.example .env
docker compose up --build
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

O serviço aguarda o healthcheck do PostgreSQL, aplica as migrações, cria as categorias iniciais, coleta os estáticos e fica disponível em [http://localhost:8000](http://localhost:8000). A documentação interativa da API fica em [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/). O endpoint `/health/` verifica a aplicação e a conexão com o banco.

### Primeiro acesso e cadastro de usuários

Na primeira execução, acesse **Criar usuário** na tela de login. A primeira conta cadastrada recebe automaticamente o perfil Administrador e acesso ao painel em [http://localhost:8000/admin/](http://localhost:8000/admin/). Assim que essa conta for criada, o cadastro público será fechado; contas novas devem ser criadas por um administrador no painel. Faça o primeiro cadastro antes de liberar o acesso aos usuários da rede.

O administrador pode alterar o perfil de uma conta para Agente ou Solicitante pelo painel. Para criar outro Administrador com privilégios de superusuário, execute:

```bash
docker compose exec web python manage.py createsuperuser
```

O repositório não contém usuários nem chamados. Esses dados são criados somente no PostgreSQL da instalação e permanecem fora do Git. As categorias iniciais são adicionadas pela migração `0003_default_categories`.

### Implantação em servidor interno com HTTPS

Use esta configuração em um servidor que será acessado por outros computadores. Configure um nome DNS interno real para o Service Desk e faça-o apontar para o servidor. A configuração de produção usa Caddy com uma autoridade certificadora interna; os computadores dos usuários precisam confiar no certificado raiz dessa autoridade.

No Windows PowerShell, copie o modelo de produção:

```powershell
Copy-Item .env.production.example .env
```

Gere valores aleatórios e substitua os campos `DJANGO_SECRET_KEY` e `POSTGRES_PASSWORD` no `.env`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Configure `SERVICEDESK_HOST`, `DJANGO_ALLOWED_HOSTS` e `DJANGO_CSRF_TRUSTED_ORIGINS` com o nome DNS interno usado pelos computadores. Restrinja as permissões do `.env` para que apenas a conta que administra o servidor possa lê-lo.

Antes de iniciar, limite temporariamente a porta 443 no firewall à estação de configuração. Inicie os serviços:

```powershell
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

Instale o certificado raiz do Caddy na estação de configuração antes de abrir o sistema. Isso permite que o navegador valide o HTTPS durante o cadastro inicial, sem ignorar o aviso de certificado. A porta 80 serve apenas para redirecionar para HTTPS; a porta 8000 fica vinculada ao próprio servidor e não deve ser liberada no firewall.

Para confiar na autoridade certificadora interna nos computadores Windows, copie o certificado raiz do Caddy e instale-o no repositório de certificados do usuário:

```powershell
docker compose -f docker-compose.yml -f docker-compose.production.yml cp proxy:/data/caddy/pki/authorities/local/root.crt .\servicedesk-root.crt
Import-Certificate -FilePath .\servicedesk-root.crt -CertStoreLocation Cert:\CurrentUser\Root
```

Depois de confiar no certificado, abra `https://<SERVICEDESK_HOST>/`, cadastre o primeiro usuário e confirme o acesso a `/admin/`. Em seguida, libere a porta 443 para a rede interna.

Distribua o certificado raiz por um canal interno confiável. Se a organização já possui um proxy TLS e uma autoridade certificadora corporativa, prefira usar esse proxy e instalar o certificado aprovado pela equipe de infraestrutura. Mantenha `DJANGO_SECURE_SSL_REDIRECT=True` e preserve os volumes `postgres_data`, `caddy_data` e `caddy_config` em backups.

#### Configuração após cadastrar o primeiro Administrador

1. **Confirme o acesso administrativo:** entre em `/admin/` com a conta recém-criada. Ela recebe automaticamente o perfil Administrador e acesso ao painel.
2. **Crie as contas da equipe:** em **Usuários**, crie cada conta individualmente e, em **Perfis**, atribua o papel **Agente de suporte** ou **Solicitante**. Administradores podem criar agentes e solicitantes; somente um superusuário pode criar outro perfil Administrador ou alterar contas de Administrador.
3. **Prepare integrações, se necessário:** crie um usuário dedicado para cada sistema integrado. Autentique com `POST /api/token/`, guarde o token em um cofre de segredos e revogue-o em **Tokens de autenticação** quando não precisar mais dele. Não compartilhe contas pessoais.
4. **Valide a rede e os backups:** confirme que o nome DNS e o HTTPS funcionam em outra estação, libere apenas as portas necessárias no firewall e configure cópias periódicas protegidas do banco e dos volumes Caddy.

O cadastro público é encerrado automaticamente assim que a primeira conta existe e não reabre ao desativá-la ou removê-la. Cadastros posteriores são feitos por um Administrador no painel.

### Endereços principais

| Recurso | Endereço |
| --- | --- |
| Aplicação | [http://localhost:8000/](http://localhost:8000/) |
| Administração | [http://localhost:8000/admin/](http://localhost:8000/admin/) |
| API REST | [http://localhost:8000/api/v1/](http://localhost:8000/api/v1/) |
| Documentação Swagger (somente Administradores) | [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/) |
| Esquema OpenAPI (somente Administradores) | [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/) |
| Verificação de saúde | [http://localhost:8000/health/](http://localhost:8000/health/) |

### Acesso à API

Autentique com `POST /api/token/`, enviando `username` e `password`; a resposta contém o token e a data de expiração. Envie-o nas chamadas como `Authorization: Token <token>`. Os tokens expiram após 30 dias por padrão; um Administrador pode revogá-los antes disso pelo painel, em “Tokens de autenticação”. Ajuste `API_TOKEN_LIFETIME_DAYS` se a política da organização exigir validade menor.

O DRF mantém um token por usuário. Para isolar integrações, crie uma conta dedicada para cada sistema externo, gere seu token e armazene-o em um gestor de segredos. Renove o token antes de sua expiração e após qualquer suspeita de vazamento.

### Testes e verificações

```bash
docker compose exec web pytest
docker compose exec web python manage.py makemigrations --check --dry-run
```

O workflow do GitHub Actions executa essas verificações em pull requests e atualizações das branches `main` e `master`, usando PostgreSQL real.

## Desenvolvimento sem Docker

É necessário Python 3.13+, PostgreSQL e as variáveis de `.env`. Crie um ambiente virtual, instale as dependências e aponte `POSTGRES_HOST` para o host local:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

No Windows, use os equivalentes em `.venv\\Scripts`. O banco principal é sempre PostgreSQL; SQLite não é usado. A configuração sem Docker não instala proxy TLS automaticamente; use um proxy HTTPS corporativo e defina as variáveis de produção antes de disponibilizar a aplicação na rede.

## Operação e manutenção

- As credenciais ficam apenas em variáveis de ambiente; nunca versione `.env`.
- Para reinicializar os dados locais, execute `docker compose down -v` e depois `docker compose up --build`. Isso remove o volume de desenvolvimento do PostgreSQL.
- Se a aplicação não conectar ao banco, verifique `docker compose logs db` e confirme os valores de `POSTGRES_*` no `.env`.
- Em produção, defina `DJANGO_DEBUG=False`, uma chave secreta forte, hosts permitidos e TLS na borda. Cookies seguros são habilitados fora do modo de depuração; o redirecionamento HTTPS depende de `DJANGO_SECURE_SSL_REDIRECT=True`.
- Configure `SERVICEDESK_SLA_HOURS` (padrão 72) para o indicador de chamados abertos fora do prazo.
- Para gerar backup PostgreSQL sob demanda, execute `docker compose --profile ops run --rm backup` (em produção, inclua também `-f docker-compose.production.yml`). Os arquivos são gravados no diretório definido em `BACKUP_DIR` (padrão `./backups`). Restrinja o acesso e criptografe os backups fora do servidor; para restaurar, use `pg_restore` contra uma base previamente criada e teste a restauração periodicamente.
- Logs da aplicação são emitidos em JSON para stdout/stderr. O healthcheck do container web consulta `/health/` e valida o PostgreSQL.
- `DJANGO_SECRET_KEY` é obrigatória. Em produção, habilite `DJANGO_SECURE_SSL_REDIRECT=True` somente quando TLS estiver configurado no proxy; o HSTS é ativado quando essa opção está habilitada fora de DEBUG.

## Limitações conhecidas

A API aceita autenticação por sessão e por token revogável. Para ambientes com requisitos corporativos mais rígidos, recomenda-se adotar tokens rotativos ou OIDC. O envio de e-mail e SLAs por calendário não foram incluídos; indicadores de tempo consideram a duração entre abertura e resolução registrada.

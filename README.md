# Service Desk

Sistema web para abertura, distribuição e acompanhamento de chamados internos, construído com Django, Django REST Framework e PostgreSQL. A interface é responsiva e oferece visões diferentes para solicitantes, agentes e administradores.

## Recursos entregues

- Login seguro com os mecanismos nativos do Django e rotas protegidas.
- Perfis `Administrador`, `Agente de suporte` e `Solicitante`.
- Abertura, listagem, busca e filtros por status, prioridade e categoria.
- Atribuição, mudança de categoria/prioridade, transições controladas de status, resolução, encerramento e reabertura.
- Comentários públicos e notas internas, com visibilidade protegida.
- Histórico de auditoria para alterações, comentários e transições do chamado.
- Indicadores de fila, prioridade e tempo médio de resolução calculados a partir dos dados reais.
- API REST paginada, com busca, filtros, ordenação, documentação Swagger e as mesmas regras de visibilidade da interface.
- Autenticação externa da API por token revogável (DRF Token Authentication).
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
| Excluir chamado | Não | Não | Django Admin; pela API somente como superusuário |

Transições permitidas: **Aberto → Em andamento/Encerrado**, **Em andamento → Aguardando solicitante/Resolvido/Encerrado**, **Aguardando solicitante → Em andamento/Resolvido/Encerrado**, **Resolvido → Encerrado/Em andamento** e **Encerrado → Em andamento** (reabertura). Atribuições exigem um agente ou administrador ativo.

Usuários inativos não conseguem autenticar-se; responsáveis inativos são recusados pela validação do modelo. O perfil Administrador recebe acesso ao Django Admin e às permissões de gerenciamento do sistema. Um Administrador pode classificar outras contas como Agente ou Solicitante. A criação de outro Administrador e o gerenciamento de superusuários exigem uma conta de superusuário criada pelo comando `createsuperuser`.

Alterações relevantes registram responsável, data e valores anterior/posterior. Edições e exclusões de comentários também geram auditoria. Os registros não podem ser editados pelo domínio da aplicação, mas acompanham o ciclo de vida do chamado e são removidos se um administrador excluir o chamado.

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

### Primeiro acesso

Na primeira execução, acesse **Criar usuário** na tela de login. A primeira conta cadastrada recebe automaticamente o perfil Administrador e acesso ao painel em [http://localhost:8000/admin/](http://localhost:8000/admin/). Faça esse cadastro antes de disponibilizar uma instalação nova em uma rede pública.

As contas criadas depois dela recebem o perfil Solicitante. O administrador pode promovê-las a Agente ou mantê-las como Solicitante pelo painel. Caso seja necessário criar outro Administrador, execute:

```bash
docker compose exec web python manage.py createsuperuser
```

O repositório não contém usuários nem chamados. Esses dados são criados somente no PostgreSQL da instalação e permanecem fora do Git. As categorias iniciais são adicionadas pela migração `0003_default_categories`.

### Endereços principais

| Recurso | Endereço |
| --- | --- |
| Aplicação | [http://localhost:8000/](http://localhost:8000/) |
| Administração | [http://localhost:8000/admin/](http://localhost:8000/admin/) |
| API REST | [http://localhost:8000/api/v1/](http://localhost:8000/api/v1/) |
| Documentação Swagger | [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/) |
| Esquema OpenAPI | [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/) |
| Verificação de saúde | [http://localhost:8000/health/](http://localhost:8000/health/) |

### Acesso à API

Autentique com `POST /api/token/`, enviando `username` e `password`; a resposta contém o token. Envie-o nas chamadas como `Authorization: Token <token>`. Um administrador pode revogar o token apagando-o no Django Admin em “Tokens de autenticação”.

O DRF mantém um token por usuário. Para isolar integrações, crie uma conta dedicada para cada sistema externo, gere seu token e armazene-o em um gestor de segredos.

### Testes e verificações

```bash
docker compose exec web pytest
docker compose exec web python manage.py makemigrations --check --dry-run
```

O workflow do GitHub Actions executa essas verificações em pull requests e está configurado para atualizações da branch `main`, usando PostgreSQL real. Se o repositório utilizar `master` como branch principal, ajuste `branches` em `.github/workflows/ci.yml`.

## Desenvolvimento sem Docker

É necessário Python 3.13+, PostgreSQL e as variáveis de `.env`. Crie um ambiente virtual, instale as dependências e aponte `POSTGRES_HOST` para o host local:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

No Windows, use os equivalentes em `.venv\\Scripts`. O banco principal é sempre PostgreSQL; SQLite não é usado.

## Operação e manutenção

- As credenciais ficam apenas em variáveis de ambiente; nunca versione `.env`.
- Para reinicializar os dados locais, execute `docker compose down -v` e depois `docker compose up --build`. Isso remove o volume de desenvolvimento do PostgreSQL.
- Se a aplicação não conectar ao banco, verifique `docker compose logs db` e confirme os valores de `POSTGRES_*` no `.env`.
- Em produção, defina `DJANGO_DEBUG=False`, uma chave secreta forte, hosts permitidos e TLS na borda. Cookies seguros são habilitados fora do modo de depuração; o redirecionamento HTTPS depende de `DJANGO_SECURE_SSL_REDIRECT=True`.
- Configure `SERVICEDESK_SLA_HOURS` (padrão 72) para o indicador de chamados abertos fora do prazo.
- Para gerar backup PostgreSQL sob demanda, execute `docker compose --profile ops run --rm backup`. Os arquivos são gravados no diretório definido em `BACKUP_DIR` (padrão `./backups`). Para restaurar, use `pg_restore` contra uma base previamente criada; teste a restauração periodicamente.
- Logs da aplicação são emitidos em JSON para stdout/stderr. O healthcheck do container web consulta `/health/` e valida o PostgreSQL.
- `DJANGO_SECRET_KEY` é obrigatória. Em produção, habilite `DJANGO_SECURE_SSL_REDIRECT=True` somente quando TLS estiver configurado no proxy; o HSTS é ativado quando essa opção está habilitada fora de DEBUG.

## Limitações conhecidas

A API aceita autenticação por sessão e por token revogável. Para ambientes com requisitos corporativos mais rígidos, recomenda-se adotar tokens rotativos ou OIDC. O envio de e-mail e SLAs por calendário não foram incluídos; indicadores de tempo consideram a duração entre abertura e resolução registrada.

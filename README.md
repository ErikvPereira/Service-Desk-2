# Service Desk

Aplicação corporativa para abertura, distribuição e acompanhamento de chamados, construída com Django e PostgreSQL. A interface foi projetada para leitura rápida das filas e dos estados de atendimento, com design responsivo inspirado na referência fornecida.

## Recursos entregues

- Login seguro com os mecanismos nativos do Django e rotas protegidas.
- Perfis `Administrador`, `Agente de suporte` e `Solicitante`.
- Abertura, listagem, busca e filtros por status, prioridade e categoria.
- Atribuição, mudança de categoria/prioridade, transições controladas de status, resolução, encerramento e reabertura.
- Comentários públicos e notas internas, com visibilidade protegida.
- Histórico imutável de auditoria para operações relevantes.
- Indicadores de fila, prioridade e tempo médio de resolução calculados a partir dos dados reais.
- API REST paginada, com busca, filtros, ordenação, documentação Swagger e as mesmas regras de visibilidade da interface.
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
| Gerenciar usuários e cadastros de apoio | Não | Django Admin (superusuário) | Django Admin (superusuário) |
| Excluir chamado | Não | Não | Somente superusuário pela API/Admin |

Transições permitidas: **Aberto → Em andamento/Encerrado**, **Em andamento → Aguardando solicitante/Resolvido/Encerrado**, **Aguardando solicitante → Em andamento/Resolvido/Encerrado**, **Resolvido → Encerrado/Em andamento** e **Encerrado → Em andamento** (reabertura). Atribuições exigem um agente ou administrador ativo. Registros de auditoria não podem ser alterados nem excluídos pelo domínio da aplicação.

Usuários inativos não conseguem autenticar-se; responsáveis inativos são recusados pela validação do modelo. Todas as operações relevantes são registradas com responsável, data e valores anterior/posterior quando houver mudança de campo.

## Executar com Docker

Pré-requisito: Docker com Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

O serviço aguarda o healthcheck do PostgreSQL, aplica as migrações e fica disponível em [http://localhost:8000](http://localhost:8000). A documentação interativa da API fica em [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/).

Crie o primeiro administrador em outro terminal:

```bash
docker compose exec web python manage.py createsuperuser
```

O administrador também pode cadastrar categorias, usuários e perfis em [http://localhost:8000/admin/](http://localhost:8000/admin/). Após criar usuários, ajuste seu perfil para Agente ou Administrador nessa tela quando necessário.

### Testes e verificações

```bash
docker compose exec web pytest
docker compose exec web python manage.py makemigrations --check --dry-run
```

O pipeline repete essas verificações em pull requests e atualizações da branch `main`, usando PostgreSQL real.

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
- Em produção, defina `DJANGO_DEBUG=False`, uma chave secreta forte, hosts permitidos e TLS na borda. As opções de cookie seguro e redirecionamento HTTPS já são habilitadas fora do modo de depuração.

## Limitações conhecidas

O projeto usa autenticação por sessão para a API, adequada à aplicação web integrada. Para clientes externos, recomenda-se acrescentar tokens rotativos/OIDC conforme a política corporativa. O envio de e-mail e SLAs por calendário não foram incluídos; indicadores de tempo consideram a duração entre abertura e resolução registrada.

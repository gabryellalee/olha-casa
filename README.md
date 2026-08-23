# Olha Casa

Monitor gratuito de T0 e T1 na zona Porto–Trofa, com triagem automática e alertas enviados pelo `@olhacasa_bot` para o grupo **Alertas Casinhas**.

O projeto consulta diretamente páginas públicas do Idealista, Imovirtual, SUPERCASA e Casa Sapo. Não usa emails, n8n, servidor permanente, subscrição nem modelo de IA pago.

## O que faz

- Executa a pesquisa a cada 30 minutos no GitHub Actions.
- Deteta anúncios novos, descidas de preço e possíveis republicações.
- Elimina duplicados entre portais através de uma impressão do imóvel.
- Envia todos os T0/T1 até 750 € dentro das zonas aceites.
- Inclui Vila Nova de Famalicão e Paços de Ferreira, além do polígono aproximado original.
- Mostra área, percurso ao ISCAP, andar, elevador e estacionamento quando disponíveis, sem usar esses dados para bloquear alertas.
- Analisa espaço para duas pessoas em teletrabalho, fibra, ruído e luz apenas como informação.
- Extrai cauções, rendas adiantadas, entrada inicial, fiador, documentos, despesas, contrato, cozinha e animais.
- Calcula renda por m², compara com a amostra recolhida e assinala riscos de fraude.
- Cria uma explicação, perguntas em falta e uma mensagem pronta para o senhorio.

## Instalação no GitHub

1. Crie um repositório no GitHub e coloque nele o conteúdo desta pasta. Pode ser privado.
2. No Telegram, adicione o `@olhacasa_bot` ao grupo **Alertas Casinhas** e permita-lhe enviar mensagens.
3. Guarde o token criado pelo BotFather. Nunca o escreva num ficheiro do repositório.
4. Envie uma mensagem no grupo depois de adicionar o bot. Assim, o sistema consegue descobrir automaticamente o grupo **Alertas Casinhas**.
5. Em **Settings → Secrets and variables → Actions**, crie `TELEGRAM_BOT_TOKEN`.
   `TELEGRAM_CHAT_ID` é opcional e só é necessário se o bot pertencer a vários grupos.
6. Em **Settings → Actions → General → Workflow permissions**, selecione **Read and write permissions**.
7. Abra **Actions → Procurar casas → Run workflow** para testar.

A primeira execução aprende os anúncios que já existem e envia uma confirmação de que o monitor ficou ligado, mas não envia esses anúncios antigos. As seguintes enviam apenas novidades relevantes. Se não surgir nenhuma novidade, o bot envia uma confirmação semanal de que continua ativo.

## Teste local

Requer Python 3.11 ou superior.

```bash
python -m venv .venv
. .venv/bin/activate
pip install ".[test]"
pytest -q
python -m olha_casa.main --config config.example.yml --dry-run
```

## Configuração

Os critérios, o polígono e os URLs de pesquisa estão em `config.example.yml`. Este ficheiro não contém segredos e pode ser editado diretamente.

O círculo desenhado no mapa foi convertido numa aproximação geográfica. Quando o portal só mostra a freguesia, a decisão também é aproximada e o alerta identifica informação por confirmar.

A viagem de carro usa uma rota rodoviária, quando o anúncio fornece coordenadas, acrescida de uma margem conservadora para hora de ponta e para a imprecisão da localização. Sem coordenadas, usa uma estimativa por zona. Menções a metro, autocarro ou transportes públicos dão um pequeno bónus.

## Estado e privacidade

O histórico fica em `data/state.json` e é atualizado pelo próprio workflow. Guarda apenas campos normalizados, ligações públicas e histórico de preços; não copia integralmente as descrições dos anúncios.

Os segredos do Telegram são lidos apenas do ambiente do GitHub Actions. Não aparecem no código nem no histórico.

## Limitações importantes

- O agendamento do GitHub é de melhor esforço. Pode sofrer atrasos em períodos de carga.
- Os portais alteram o HTML e podem bloquear endereços do GitHub. Cada coletor respeita `robots.txt` e não tenta contornar CAPTCHA, login ou outras proteções.
- A disponibilidade de estacionamento, fibra, silêncio e luz só pode ser confirmada numa visita ou junto do senhorio.
- A sinalização de fraude é heurística. Nunca transfira dinheiro antes de verificar o imóvel, a identidade do anunciante e o contrato.
- Os URLs de pesquisa podem precisar de atualização quando um portal muda a sua navegação. O relatório da execução mostra as fontes que falharam.

## Ajustar os alertas

Os principais valores encontram-se nas secções `search`, `home_office`, `geo` e `routing` de `config.example.yml`. Para adicionar uma pesquisa, coloque o URL público em `sources[].search_urls`, sempre no domínio do respetivo portal.

# Fotos Duplicadas

Programa para analisar pastas (e todas as subpastas) com fotos e imagens e
encontrar **duplicadas, mesmo com nomes e formatos diferentes**.

Ele encontra:

- **Cópias idênticas** (mesmo conteúdo byte a byte), mesmo com outro nome ou em outra pasta.
- **A mesma imagem em outro formato** (JPG, PNG, WEBP, BMP, TIFF, GIF, HEIC...).
- **A mesma imagem redimensionada ou recomprimida** (ex.: a versão menor enviada pelo WhatsApp).

> O programa **nunca apaga nada**. Você revisa os grupos e, se quiser, ele
> **move** as duplicadas para uma pasta que você escolher (com confirmação).
> Depois de conferir, você mesmo apaga essa pasta.

## Como usar no Windows

### Jeito mais fácil: executável

Dê dois cliques em **`FotosDuplicadas.exe`**. Não precisa ter Python
instalado. (Se você só tem o código, gere o .exe com **`Gerar executavel.bat`**,
que precisa de Python na primeira vez.)

O Windows pode mostrar "O Windows protegeu o computador" na primeira vez,
porque o programa não é assinado digitalmente. Clique em **Mais informações →
Executar assim mesmo**.

### Pelo Python

1. Instale o Python 3.10 ou mais novo em <https://www.python.org/downloads/>.
   Na instalação, marque **"Add python.exe to PATH"**.
2. Dê dois cliques em **`Abrir Fotos Duplicadas.bat`**.
   Na primeira vez ele prepara tudo sozinho (leva cerca de um minuto).
3. Na janela:
   - **Adicionar pasta…** e escolha a pasta de fotos (pode adicionar várias).
   - Escolha a **sensibilidade** (a "Normal" é a recomendada).
   - Clique em **Procurar duplicadas**.
   - Cada grupo mostra os arquivos que são a mesma imagem. O programa já marca
     (☑) as cópias sugeridas para mover e deixa desmarcada a de **maior
     resolução** em cada grupo. Clique na coluna "Mover?" para mudar.
   - Clique num arquivo para ver a prévia; duplo clique abre a imagem.
   - **Mover marcadas para outra pasta…** move as marcadas (mantendo a
     estrutura de subpastas e sem sobrescrever nada).
   - **Exportar relatório (CSV)** gera uma planilha que abre no Excel.

### Sensibilidade

| Opção | O que encontra |
|---|---|
| Somente cópias idênticas | Só arquivos exatamente iguais byte a byte. |
| Rigorosa | A mesma foto em outro formato ou tamanho. |
| Normal (padrão) | A mesma foto, inclusive versões bem comprimidas (ex.: WhatsApp). |
| Ampla | Tolera compressão muito pesada. Revise os grupos com cuidado. |

Fotos **tiradas em sequência** (a pessoa mexeu, a câmera tremeu, a luz mudou)
**não** são consideradas duplicadas em nenhuma das opções: cada par suspeito é
confirmado comparando as duas imagens bloco a bloco.

## Linha de comando (opcional)

```bat
.venv\Scripts\python -m fotosduplicadas "F:\Fotos"
.venv\Scripts\python -m fotosduplicadas "F:\Fotos" "D:\Backup" --csv relatorio.csv
.venv\Scripts\python -m fotosduplicadas "F:\Fotos" --sensibilidade rigorosa --mover "F:\Duplicadas"
```

`--mover` pergunta antes de mover qualquer coisa.

## Como funciona

1. Lista todas as imagens das pastas, incluindo subpastas.
2. Calcula o **SHA-256** de cada arquivo (cópias idênticas).
3. Calcula dois **hashes perceptuais** de 64 bits (dHash e aHash) sobre a
   imagem reduzida em tons de cinza, respeitando a rotação EXIF. Imagens que
   são a mesma foto têm hashes quase iguais, independentemente de nome,
   formato, tamanho ou compressão.
4. Os hashes só apontam **candidatas** (usando uma árvore BK, então funciona
   bem com dezenas de milhares de fotos). Cada par candidato precisa ter a
   mesma proporção e passar por uma **confirmação**: as duas imagens são
   reduzidas para 64x64 e comparadas em blocos de 4x4 pixels. Se qualquer
   bloco mudou (um braço que mexeu, um rosto que virou), não é duplicada.
5. Em cada grupo, sugere manter a de maior resolução (depois a maior em bytes).

## Desenvolvimento

```bash
pip install Pillow pytest
python -m pytest
```

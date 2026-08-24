import logging
import os
import requests
import threading
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters
from google import genai

# ==============================================================================
# CONFIGURAÇÕES (Lidas do ambiente com valores padrão de teste)
# ==============================================================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8885286627:AAG6Hdy0DPcJ8iT2TBJJ-mKfgFuWVuIVWl0")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6K0bBoQYygLOmzUlZxv3vWeBpgnFVIW1DZAt1nFt_5QVA")
ELYTE_CLIENT_ID = os.environ.get("ELYTE_CLIENT_ID", "ep_e8cf32376f3735c22abadd9348e109e9")
ELYTE_CLIENT_SECRET = os.environ.get("ELYTE_CLIENT_SECRET", "eps_761f10b08555c5b12b1792b26a0743d0d3cbdc4cbcf3a60d23f1b8ad6fdc0e1f")
ELYTE_PAY_API_URL = "https://api.elytepay.com.br/v1/checkout"

SYSTEM_PROMPT = """
Você é um assistente virtual de atendimento.
Responda às dúvidas dos clientes de forma educada, simpática e objetiva.
Quando perguntarem sobre valores, assinaturas ou opções disponíveis, oriente o cliente a ver o menu usando o comando /opcoes.
"""

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
bot_telegram = Bot(token=TELEGRAM_TOKEN)
app_flask = Flask(__name__)

# ==============================================================================
# ESTRUTURA DE PLANOS (Valores em centavos)
# ==============================================================================
PLANOS = {
    "plano_1": {
        "nome": "Plano Base 3 Dias", 
        "valor": 989, 
        "texto_valor": "R$ 9,89"
    },
    "plano_2": {
        "nome": "Plano VIP 7 Dias", 
        "valor": 1519, 
        "texto_valor": "R$ 15,19"
    },
    "plano_3": {
        "nome": "Plano Completo 14 Dias", 
        "valor": 2500, 
        "texto_valor": "R$ 25,00"
    },
    "plano_4": {
        "nome": "Plano Completo Full Acesso 90 Dias", 
        "valor": 3459, 
        "texto_valor": "R$ 34,59"
    }
}

# ==============================================================================
# INTEGRAÇÃO COM GATEWAY DE PAGAMENTO (GERAÇÃO DE PIX)
# ==============================================================================
def solicitar_pix_gateway(plano_id, user_id):
    plano = PLANOS.get(plano_id)
    if not plano:
        return None

    headers = {
        "x-client-id": ELYTE_CLIENT_ID,
        "x-client-secret": ELYTE_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    
    payload = {
        "amount": plano["valor"],
        "description": plano["nome"],
        "external_id": str(user_id),
        "payment_method": "pix"
    }

    try:
        response = requests.post(ELYTE_PAY_API_URL, json=payload, headers=headers, timeout=5)
        if response.status_code in [200, 201]:
            dados = response.json()
            return dados.get("pix_code")
    except Exception as e:
        logging.error(f"Erro na API de Pagamento: {e}")

    return None

# ==============================================================================
# ROTA DE WEBHOOK (RECEPÇÃO DE PAGAMENTOS DA ELYTE PAY)
# ==============================================================================
@app_flask.route('/webhook/elyte', methods=['POST'])
def webhook_elyte():
    data = request.json or {}
    
    status = data.get("status")
    user_id = data.get("external_id")
    
    if status in ["paid", "approved", "completed"] and user_id:
        try:
            bot_telegram.send_message(
                chat_id=int(user_id),
                text="✅ *Pagamento confirmado com sucesso!*\n\nSeja bem-vindo(a)! Seu acesso foi liberado.",
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem de confirmação no Telegram: {e}")
            
    return {"status": "success"}, 200

def rodar_flask():
    port = int(os.environ.get("PORT", 5000))
    app_flask.run(host="0.0.0.0", port=port)

# ==============================================================================
# COMANDOS E INTERAÇÃO COM O TELEGRAM
# ==============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = update.effective_user.first_name
    await update.message.reply_text(f"Olá, {nome}! Seja bem-vindo(a). Digite /opcoes para visualizar os planos disponíveis.")

async def enviar_menu_opcoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Plano Base 3 Dias - R$ 9,89", callback_data="plano_1")],
        [InlineKeyboardButton("Plano VIP 7 Dias - R$ 15,19", callback_data="plano_2")],
        [InlineKeyboardButton("Plano Completo 14 Dias - R$ 25,00", callback_data="plano_3")],
        [InlineKeyboardButton("Plano Full Acesso 90 Dias - R$ 34,59", callback_data="plano_4")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    texto_menu = "Escolha uma das opções abaixo:"
    
    if update.message:
        await update.message.reply_text(texto_menu, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(texto_menu, reply_markup=reply_markup)

async def processar_opcao_escolhida(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plano_id = query.data
    user_id = query.from_user.id
    plano_info = PLANOS.get(plano_id)
    
    await query.edit_message_text(text=f"Gerando o Pix para o *{plano_info['nome']}*, aguarde um instante... ⏳", parse_mode="Markdown")
    
    pix_code = solicitar_pix_gateway(plano_id, user_id)
    
    if pix_code:
        await query.message.reply_text(
            f"Código Pix gerado com sucesso!\n\n"
            f"`{pix_code}`\n\n"
            f"Copie o código acima e cole na opção *Pix Copia e Cola* no aplicativo do seu banco.",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("Ocorreu uma falha ao gerar o Pix. Por favor, tente clicar na opção novamente.")

async def responder_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.lower()
    
    palavras_chave = ["plano", "planos", "opções", "opcoes", "preço", "preco", "valor", "quanto custa", "comprar", "pix"]
    if any(p in texto for p in palavras_chave):
        await enviar_menu_opcoes(update, context)
        return

    if not ai_client:
        await update.message.reply_text("Para atendimento automatizado via IA, é necessário configurar a GEMINI_API_KEY.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=update.message.text,
            config={'system_instruction': SYSTEM_PROMPT}
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logging.error(f"Erro no Gemini: {e}")
        await update.message.reply_text("Desculpe, tive um problema ao responder. Pode repetir?")

# ==============================================================================
# INICIALIZAÇÃO PRINCIPAL
# ==============================================================================
def main():
    threading.Thread(target=rodar_flask, daemon=True).start()

    app_telegram = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app_telegram.add_handler(CommandHandler("start", start))
    app_telegram.add_handler(CommandHandler("opcoes", enviar_menu_opcoes))
    app_telegram.add_handler(CallbackQueryHandler(processar_opcao_escolhida))
    app_telegram.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_lead))
    
    print("Bot e Webhook rodando com sucesso...")
    app_telegram.run_polling()

if __name__ == '__main__':
    main()

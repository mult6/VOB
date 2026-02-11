# 🚀 Quick Start Guide - Opinion Market Maker Bot

## Три шага до запуска

### Шаг 1: Подготовка кошелька
1. Установите [MetaMask](https://metamask.io/download/)
2. Переключитесь на **BNB Smart Chain** (Chain ID: 56)
3. Пополните BNB для gas (~$5)

### Шаг 2: Создание профиля Opinion
1. Откройте [app.opinion.trade](https://app.opinion.trade)
2. Подключите MetaMask
3. Создайте профиль
4. Пополните USDT на балансе Opinion (минимум $50)
5. **Скопируйте Multi-sig Address** из "My Profile"

### Шаг 3: Получение API ключа
1. Заполните [форму заявки Opinion](https://docs.google.com/forms/d/1h7gp8UffZeXzYQ-lv4jcou9PoRNOqMAQhyW4IwZDnII)
2. Дождитесь email с API ключом (1-3 дня)
3. Сохраните ключ: `opn_prod_xxx...`

---

## 🎯 Запуск бота

### Через веб-интерфейс (рекомендуется)

1. Откройте https://opinion-api.kirst-defi.xyz/
2. Нажмите **"Подключить MetaMask"**
3. Введите данные:
   - ✅ Opinion API Key
   - ✅ Multi-sig Address (из app.opinion.trade)
   - ✅ Настройки стратегии
4. Нажмите **"Запустить бота"**
5. Подтверждайте транзакции в MetaMask

### Локально (для разработки)

```bash
# 1. Клонируйте репозиторий
git clone <your-repo>
cd opinion

# 2. Установите зависимости
pip install -r requirements.txt

# 3. Создайте .env файл
echo "APIKEY=opn_prod_xxx..." > .env
echo "PRIVATE_KEY=0x..." >> .env
echo "MULTISIG_WALLET=0x..." >> .env

# 4. Запустите бота
python bot_v2.py
```

---

## 📋 Где что взять?

| Параметр | Где получить | Пример |
|----------|-------------|--------|
| **MetaMask адрес** | MetaMask → кликнуть на адрес | `0xABC...123` |
| **Multi-sig Address** | [app.opinion.trade](https://app.opinion.trade) → My Profile | `0x742d35...` |
| **Opinion API Key** | [Форма заявки](https://docs.google.com/forms/d/1h7gp8UffZeXzYQ-lv4jcou9PoRNOqMAQhyW4IwZDnII) | `opn_prod_...` |

---

## ⚠️ Важные отличия

### MetaMask адрес vs Multi-sig Address

```
MetaMask адрес (0xABC...)
  ↓
  Используется для:
  - Подписи транзакций
  - Оплаты gas fees
  - НЕ для хранения средств Opinion

Multi-sig Address (0x742...)
  ↓
  Используется для:
  - Хранения USDT на Opinion
  - Торговых позиций
  - Идентификации в Opinion API
  - Указывается в настройках бота
```

---

## 🔒 Безопасность

### ✅ Безопасно:
- Подключение MetaMask через веб-интерфейс
- Приватный ключ остается в MetaMask
- Multi-sig Address — публичная информация

### ❌ Никогда не делайте:
- Не вводите приватный ключ на сайтах
- Не передавайте seed фразу
- Не храните приватный ключ в незашифрованном виде

---

## 🆘 Troubleshooting

### Проблема: "Multi-sig Address не найден"
**Решение:** Создайте профиль на app.opinion.trade и скопируйте адрес из My Profile

### Проблема: "Бот не размещает ордера"
**Решение:** 
1. Проверьте баланс USDT на Opinion (минимум $50)
2. Убедитесь что Multi-sig Address правильный
3. Проверьте что API ключ активен

### Проблема: "MetaMask не подключается"
**Решение:**
1. Убедитесь что находитесь на BNB Chain
2. Перезагрузите страницу
3. Проверьте разрешения в MetaMask

---

## 📞 Поддержка

- **Документация:** [WEB3_SETUP_GUIDE.md](WEB3_SETUP_GUIDE.md)
- **Развертывание:** [WEB_DEPLOYMENT_GUIDE.md](WEB_DEPLOYMENT_GUIDE.md)
- **Opinion Docs:** [docs.opinion.trade](https://docs.opinion.trade/)

---

**Готовы начать? 🚀**

1. ✅ Создайте профиль на app.opinion.trade
2. ✅ Получите Multi-sig Address
3. ✅ Запросите API ключ
4. ✅ Запустите бота!

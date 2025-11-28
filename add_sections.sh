#!/bin/bash

# Добавление data-section для секции "Why Choose Us"
sed -i '72s/<section class="py-5">/<section class="py-5" id="section-why-choose-us" data-section="why-choose-us">/' templates/index.html

# Добавление data-section для секции "Calculator"
sed -i '124s/<section class="py-5">/<section class="py-5" id="section-calculator" data-section="calculator">/' templates/index.html

# Добавление data-section для секции "Transactions"
sed -i '215s/<section class="py-5 bg-dark">/<section class="py-5 bg-dark" id="section-transactions" data-section="transactions">/' templates/index.html

# Добавление data-section для секции "Resources"
sed -i '285s/<section class="py-5">/<section class="py-5" id="section-resources" data-section="resources">/' templates/index.html

# Добавление data-section для CTA секции
sed -i '453s/<section class="py-5 text-white text-center" style="background: linear-gradient(to right, var(--trustlendx-blue), var(--trustlendx-teal));">/<section class="py-5 text-white text-center" id="section-cta" data-section="cta" style="background: linear-gradient(to right, var(--trustlendx-blue), var(--trustlendx-teal));">/' templates/index.html

# Выполняем скрипт
chmod +x add_sections.sh
./add_sections.sh

